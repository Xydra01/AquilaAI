#include "aquila/modules/workspace_module.hpp"

#include "git_oracle.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cstdio>
#include <map>

using namespace aquila;
namespace fs = std::filesystem;

namespace {

std::map<std::string, std::string> all_bytes(const fs::path& root) {
    std::map<std::string, std::string> out;
    for (const auto& e : fs::recursive_directory_iterator(root)) {
        if (e.is_regular_file()) out[path_to_utf8(fs::relative(e.path(), root))] = test::read_bytes(e.path());
    }
    return out;
}

// A private copy of tests/fixtures/workspace/sample_repo plus files git would
// not keep (.env, build/, a non-UTF-8 file).
struct Repo {
    test::TempDir tmp;
    Repo() {
        fs::copy(test::fixture_dir() / "workspace" / "sample_repo", tmp.path(), fs::copy_options::recursive);
        tmp.write(".env", "API_KEY=secret\n");
        tmp.write("build/generated.h", "#define GENERATED 1\n");
        tmp.write("data/latin1.txt", "caf\xE9\n");
    }
    [[nodiscard]] ModuleContext ctx() const { return {tmp.path(), 4500}; }
    [[nodiscard]] std::string bytes(const std::string& rel) const { return test::read_bytes(tmp.path() / rel); }
};

ActionResult call(WorkspaceModule& m, const std::string& action, const std::string& args) {
    return m.execute_action(action, Json::parse(args));
}

Json edit_args(const std::string& file, const std::string& search, const std::string& replace) {
    return Json{{"file", file}, {"search_block", search}, {"replace_block", replace}};
}

}  // namespace

TEST_CASE("workspace: outline lists files and symbols, hides secrets and generated dirs") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    m.configure(Json::parse(R"({"pinned_files":["src/calc.cpp"]})"));
    const auto r = call(m, "outline", "{}");
    REQUIRE(r.success);
    const auto& o = r.llm_facing_output;
    INFO(o);
    CHECK(o.find("src/calc.cpp (13 lines) [pinned] | symbols: calc, Calc::sub, twice") != std::string::npos);
    CHECK(o.find("src/calc.hpp (11 lines) | symbols: calc, Calc, add") != std::string::npos);
    CHECK(o.find("py/app.py (21 lines) | symbols: cached, Store, __init__, add, check, flush") != std::string::npos);
    CHECK(o.find("README.md (3 lines)") != std::string::npos);
    CHECK(o.find(".env") == std::string::npos);
    CHECK(o.find("build/") == std::string::npos);
    CHECK(r.token_estimate == (o.size() + 3) / 4);
}

TEST_CASE("workspace: read_region and inspect_symbol") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    const auto region = call(m, "read_region", R"({"file":"src/calc.cpp","start_line":5,"end_line":7})");
    REQUIRE(region.success);
    CHECK(region.llm_facing_output ==
          "--- src/calc.cpp lines 5-7 of 13 ---\n5: int Calc::sub(int a, int b) {\n6:     return a - b;\n7: }\n");
    CHECK(call(m, "read_region", R"({"file":"src/calc.cpp","start_line":99})").error_code == "out_of_range");

    const auto sub = call(m, "inspect_symbol", R"({"file":"src/calc.cpp","name":"sub"})");
    REQUIRE(sub.success);
    CHECK(sub.llm_facing_output.rfind("--- src/calc.cpp: function Calc::sub (lines 5-7) ---\n", 0) == 0);
    const auto cached = call(m, "inspect_symbol", R"({"file":"py/app.py","name":"cached"})");
    REQUIRE(cached.success);
    CHECK(cached.llm_facing_output.find("4: @functools.cache\n5: def cached(n):") != std::string::npos);
    const auto missing = call(m, "inspect_symbol", R"({"file":"py/app.py","name":"nope"})");
    CHECK(missing.error_code == "symbol_not_found");
    CHECK(missing.llm_facing_output.find("symbols: cached, Store") != std::string::npos);
    CHECK(call(m, "inspect_symbol", R"({"file":"README.md","name":"x"})").error_code == "unsupported_language");
}

TEST_CASE("workspace: surgical_edit match rules (Python search_replace semantics)") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    CHECK(m.execute_action("surgical_edit", edit_args("src/calc.cpp", "", "x")).error_code == "empty_search");
    const auto none = m.execute_action("surgical_edit", edit_args("src/calc.cpp", "return a * b;", "x"));
    CHECK(none.error_code == "no_match");
    CHECK(none.llm_facing_output.find("File starts with: \"#include") != std::string::npos);
    CHECK(m.execute_action("surgical_edit", edit_args("src/calc.cpp", "int ", "long ")).error_code == "ambiguous_match");

    const auto ok = m.execute_action("surgical_edit", edit_args("src/calc.cpp", "return a - b;", "return b - a;"));
    REQUIRE(ok.success);
    CHECK(ok.llm_facing_output == "edited src/calc.cpp at line 6 (1 lines -> 1 lines; file now 13 lines)");
    CHECK(repo.bytes("src/calc.cpp").find("return b - a;") != std::string::npos);
}

TEST_CASE("workspace guardrail: syntax-breaking or conflict-marker edits change nothing") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    const auto before = all_bytes(repo.tmp.path());

    const auto cpp = m.execute_action("surgical_edit", edit_args("src/calc.cpp", "return a - b;", "return a - ;"));
    CHECK(cpp.error_code == "syntax_error");
    CHECK(cpp.llm_facing_output.find("cpp syntax error at line 6, column") != std::string::npos);
    const auto py = m.execute_action("surgical_edit", edit_args("py/app.py", "return n * 2", "return (n * 2"));
    CHECK(py.error_code == "syntax_error");
    const auto conflict = m.execute_action("surgical_edit",
        edit_args("README.md", "Fixture for", "<<<<<<< HEAD\nFixture for\n=======\nOther\n>>>>>>> branch\nFixture for"));
    CHECK(conflict.error_code == "conflict_marker");
    const auto brace = m.execute_action("surgical_edit", edit_args("src/calc.hpp", "};\n", "\n"));
    CHECK(brace.error_code == "syntax_error");

    CHECK(all_bytes(repo.tmp.path()) == before);  // disk untouched
    CHECK(m.pending().empty());                    // buffer untouched
    const auto snap = m.export_state_snapshot();
    for (const auto& d : snap["canvas"]["documents"]) CHECK(d["current"] == 0);

    // A file that was already broken stays editable if the edit adds no errors.
    const auto fix_other = m.execute_action("surgical_edit", edit_args("py/broken.py", "return 1", "return 10"));
    CHECK(fix_other.success);
    std::printf("guardrail: 4 bad edits refused with all %zu workspace files byte-identical\n", before.size());
}

TEST_CASE("workspace manual review: pending patch, then accept writes exactly the diff") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    m.configure(Json::parse(R"({"review":"manual"})"));
    const auto before = all_bytes(repo.tmp.path());

    const auto r = m.execute_action("surgical_edit", edit_args("src/crlf_util.cpp", "return 2;", "return 22;"));
    REQUIRE(r.success);
    CHECK(r.llm_facing_output.rfind("queued patch p1 for review: edited src/crlf_util.cpp", 0) == 0);
    CHECK(all_bytes(repo.tmp.path()) == before);
    const auto pending = m.pending();
    REQUIRE(pending.size() == 1);

    const std::string pre = repo.bytes("src/crlf_util.cpp");
    const auto accepted = m.accept(pending[0].id);
    REQUIRE(accepted.success);
    const std::string post = repo.bytes("src/crlf_util.cpp");
    CHECK(post == "int one() {\r\n    return 1;\r\n}\r\n\r\nint two() {\r\n    return 22;\r\n}\r\n");  // CRLF kept

    auto after = all_bytes(repo.tmp.path());
    auto expect = before;
    after.erase("src/crlf_util.cpp");
    expect.erase("src/crlf_util.cpp");
    CHECK(after == expect);

    CHECK(pending[0].unified_diff.find("-    return 2;\n+    return 22;\n") != std::string::npos);

    CHECK(m.accept(pending[0].id).error_code == "no_such_patch");
    std::printf("manual review: queued, accepted, CRLF preserved, %zu other files byte-identical\n", expect.size());
}

TEST_CASE("workspace manual review: git apply of the on-disk diff reproduces the accepted bytes") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    m.configure(Json::parse(R"({"review":"manual"})"));
    std::size_t checked = 0;
    for (const auto& [file, search, replace] : std::vector<std::tuple<std::string, std::string, std::string>>{
             {"src/calc.cpp", "int twice(int v) {\n    return v + v;\n}\n", "int twice(int v) {\n    return 2 * v;\n}\n\nint thrice(int v) {\n    return 3 * v;\n}\n"},
             {"src/crlf_util.cpp", "int one() {", "// first\nint one() {"},
             {"src/notes_bom.txt", "Use cmake.", "Use cmake --preset."},
             {"py/app.py", "        return len(self.items)\n", "        return len(self.items) + 0\n"}}) {
        INFO(file);
        const std::string pre = repo.bytes(file);
        REQUIRE(m.execute_action("surgical_edit", edit_args(file, search, replace)).success);
        const auto patch = m.pending().back();
        const auto module_diff = m.disk_diff(patch.id);  // the module's own patch, on-disk form
        REQUIRE_FALSE(module_diff.empty());
        REQUIRE(m.accept(patch.id).success);
        const std::string post = repo.bytes(file);
        const auto via_git = test::git_apply(file, pre, module_diff);
        INFO(module_diff);
        REQUIRE(via_git.has_value());
        CHECK(*via_git == post);
        ++checked;
    }
    std::printf("git apply oracle (module): %zu accepted edits reproduced\n", checked);
}

TEST_CASE("workspace: stale patches and external disk edits are refused") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    m.configure(Json::parse(R"({"review":"manual"})"));
    REQUIRE(m.execute_action("surgical_edit", edit_args("src/calc.cpp", "return a - b;", "return 0;")).success);
    REQUIRE(m.execute_action("surgical_edit", edit_args("src/calc.cpp", "return v + v;", "return 0;")).success);
    const auto p = m.pending();
    REQUIRE(p.size() == 2);
    REQUIRE(m.accept(p[0].id).success);
    CHECK(m.accept(p[1].id).error_code == "stale_patch");

    REQUIRE(m.execute_action("surgical_edit", edit_args("README.md", "Fixture", "A fixture")).success);
    repo.tmp.write("README.md", "changed by someone else\n");
    CHECK(m.accept(m.pending().back().id).error_code == "disk_changed");
    CHECK(repo.bytes("README.md") == "changed by someone else\n");
}

TEST_CASE("workspace: encodings, blocked paths, create and revert") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    CHECK(call(m, "read_region", R"({"file":"data/latin1.txt","start_line":1})").error_code == "unsupported_encoding");
    CHECK(call(m, "read_region", R"({"file":".env","start_line":1})").error_code == "path_blocked");
    CHECK(call(m, "read_region", R"({"file":"../escape.txt","start_line":1})").error_code == "path_outside_root");
    CHECK(call(m, "read_region", R"({"file":"build/generated.h","start_line":1})").success);  // read OK
    CHECK(m.execute_action("surgical_edit", edit_args("build/generated.h", "1", "2")).error_code == "path_blocked");

    REQUIRE(m.execute_action("surgical_edit", edit_args("src/notes_bom.txt", "Use cmake.", "Use ninja.")).success);
    CHECK(repo.bytes("src/notes_bom.txt") == "\xEF\xBB\xBF" "Build notes\nUse ninja.\n");

    const auto bad_new = m.execute_action("create_file", Json{{"file", "src/new.cpp"}, {"content", "int f( {\n"}});
    CHECK(bad_new.error_code == "syntax_error");
    CHECK_FALSE(fs::exists(repo.tmp.path() / "src" / "new.cpp"));
    const auto good_new = m.execute_action("create_file", Json{{"file", "src/new.cpp"}, {"content", "int f() { return 1; }\n"}});
    REQUIRE(good_new.success);
    CHECK(repo.bytes("src/new.cpp") == "int f() { return 1; }\n");
    CHECK(m.execute_action("create_file", Json{{"file", "src/new.cpp"}, {"content", ""}}).error_code == "exists");

    REQUIRE(m.execute_action("surgical_edit", edit_args("README.md", "Fixture for", "Changed")).success);
    REQUIRE(call(m, "revert_file", R"({"file":"README.md"})").success);
    CHECK(repo.bytes("README.md") == "# sample_repo\n\nFixture for WorkspaceModule tests.\n");
    REQUIRE(m.undo("README.md").success);  // the revert itself is undoable
    CHECK(repo.bytes("README.md").find("Changed") != std::string::npos);
}

TEST_CASE("workspace: snapshot export/restore round-trips and restored patches apply") {
    Repo repo;
    WorkspaceModule a(repo.ctx());
    a.configure(Json::parse(R"({"review":"manual","pinned_files":["src/calc.cpp"],"max_output_chars":2000})"));
    REQUIRE(a.execute_action("surgical_edit", edit_args("src/calc.cpp", "return a - b;", "return a - b - 0;")).success);
    REQUIRE(a.accept(a.pending().back().id).success);
    REQUIRE(a.execute_action("surgical_edit", edit_args("py/app.py", "return n * 2", "return n * 3")).success);
    const auto snap = a.export_state_snapshot();

    WorkspaceModule b(repo.ctx());
    b.restore_state_snapshot(snap);
    CHECK(json_io::canonical_dump(b.export_state_snapshot()) == json_io::canonical_dump(snap));
    REQUIRE(b.pending().size() == 1);
    REQUIRE(b.accept(b.pending()[0].id).success);
    CHECK(repo.bytes("py/app.py").find("return n * 3") != std::string::npos);
    REQUIRE(b.undo("src/calc.cpp").success);  // undo history survived
    CHECK(repo.bytes("src/calc.cpp").find("return a - b;") != std::string::npos);

    Json bad = snap;
    bad["review"] = "sometimes";
    WorkspaceModule c(repo.ctx());
    CHECK_THROWS_AS(c.restore_state_snapshot(bad), SchemaError);
    std::printf("snapshot: %zu bytes, round-trip byte-equal\n", json_io::canonical_dump(snap).size());
}

TEST_CASE("workspace: configure is strict") {
    Repo repo;
    WorkspaceModule m(repo.ctx());
    CHECK_THROWS_AS(m.configure(Json::parse(R"({"root":"."})")), SchemaError);
    CHECK_THROWS_AS(m.configure(Json::parse(R"({"root_dir":"../.."})")), SchemaError);
    CHECK_THROWS_AS(m.configure(Json::parse(R"({"root_dir":"missing"})")), SchemaError);
    CHECK_THROWS_AS(m.configure(Json::parse(R"({"max_output_chars":10})")), SchemaError);
    CHECK_NOTHROW(m.configure(Json::parse(R"({"root_dir":"src","review":"auto"})")));
    const auto r = call(m, "outline", "{}");
    CHECK(r.llm_facing_output.rfind("WORKSPACE: src (", 0) == 0);
}
