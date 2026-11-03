// C++ behavior against outputs recorded from the real Python implementation
// (tests/fixtures/python/gen_python_fixtures.py, pinned 759212a), where Python is correct.
#include "aquila/canvas/diff.hpp"
#include "aquila/modules/workspace_module.hpp"
#include "aquila/workspace/syntax.hpp"

#include "fixtures.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstdio>
#include <map>

using namespace aquila;

namespace {

Json oracle(const char* name) {
    return Json::parse(test::read_bytes(test::fixture_dir() / "python" / "workspace" / name));
}

}  // namespace

TEST_CASE("oracle: surgical_edit matches Python search_replace") {
    const std::map<std::string, std::string> category = {
        {"", "ok"}, {"no_match", "no_match"}, {"ambiguous_match", "ambiguous"}, {"empty_search", "empty_search"}};
    std::size_t checked = 0;
    for (const auto& c : oracle("search_replace.json")) {
        const auto name = c["case"].get<std::string>();
        INFO(name);
        test::TempDir tmp;
        tmp.write(name + ".txt", c["content"].get<std::string>());
        WorkspaceModule m({tmp.path(), 4500});
        const auto r = m.execute_action("surgical_edit", Json{{"file", name + ".txt"},
                                                              {"search_block", c["search"]},
                                                              {"replace_block", c["replace"]}});
        REQUIRE(category.count(r.error_code) == 1);
        CHECK(category.at(r.error_code) == c["category"].get<std::string>());
        CHECK(test::read_bytes(tmp.path() / (name + ".txt")) == c["result_text"].get<std::string>());
        ++checked;
    }
    std::printf("oracle search_replace: %zu cases match Python\n", checked);
    CHECK(checked == 7);
}

TEST_CASE("oracle: diff::apply matches Python apply_unified_patch on single-hunk patches") {
    std::size_t checked = 0;
    for (const auto& c : oracle("unified_patch.json")) {
        INFO(c["case"].get<std::string>());
        REQUIRE(c["ok"].get<bool>());
        std::string err;
        const auto r = diff::apply(c["content"].get<std::string>(), c["patch"].get<std::string>(), err);
        INFO(err);
        REQUIRE(r.has_value());
        CHECK(*r == c["result"].get<std::string>());
        ++checked;
    }
    std::printf("oracle unified_patch: %zu cases match Python\n", checked);
    CHECK(checked == 5);
}

TEST_CASE("oracle: tree-sitter Python symbols equal Python ast.walk names (as multisets)") {
    std::size_t checked = 0;
    for (const auto& c : oracle("python_symbols.json")) {
        INFO(c["case"].get<std::string>());
        std::vector<std::string> py = c["names"].get<std::vector<std::string>>();
        std::vector<std::string> cpp;
        for (const auto& s : syntax::symbols(syntax::Language::python, c["source"].get<std::string>())) cpp.push_back(s.name);
        std::sort(py.begin(), py.end());
        std::sort(cpp.begin(), cpp.end());
        CHECK(cpp == py);
        ++checked;
    }
    std::printf("oracle python symbols: %zu sources match ast.walk\n", checked);
    CHECK(checked == 3);
}

TEST_CASE("oracle: firewall verdicts vs Python is_safe_path, with every divergence explained") {
    // Paths where C++ deliberately differs from Python (R19), and why.
    const std::map<std::string, std::string> divergences = {
        {"state.json", "Python blocks its own state-file name; an ordinary name in user repos"},
        {".gitignore", "an ordinary project file"},
        {"server.log", "reading logs (build/test output) is allowed"},
        {"Agent-Logs/session_1.txt", "Aquila data dir name; meaningless inside a user workspace"},
        {"vector_db/data.bin", "Aquila data dir name; meaningless inside a user workspace"},
        {"__pycache__/main.cpython-310.pyc", "generated dirs are readable; writes are blocked"},
        {"build/out.o", "generated dirs are readable; writes are blocked"},
        {"node_modules/x/index.js", "generated dirs are readable; writes are blocked"},
        {".vscode/settings.json", "IDE dirs are readable; writes are blocked"},
        {"src/.env.local", "C++ also blocks .env.* variants (Python only blocks exactly .env)"},
        {"home/id_rsa", "C++ blocks SSH private keys"},
    };
    test::TempDir tmp;
    const PathFirewall fw(tmp.path());
    std::size_t agree = 0;
    std::size_t diverge = 0;
    for (const auto& c : oracle("is_safe_path.json")) {
        const auto path = c["path"].get<std::string>();
        INFO(path);
        bool cpp_ok = true;
        try {
            (void)fw.resolve(path, Access::read);
        } catch (const PathDenied&) {
            cpp_ok = false;
        }
        const bool py_ok = c["python_safe"].get<bool>();
        if (cpp_ok == py_ok) {
            CHECK(divergences.count(path) == 0);  // listed divergences must really diverge
            ++agree;
        } else {
            CHECK(divergences.count(path) == 1);
            ++diverge;
        }
        if (divergences.count(path) != 0 && path == "__pycache__/main.cpython-310.pyc") {
            CHECK_THROWS_AS(fw.resolve(path, Access::write), PathDenied);
        }
    }
    std::printf("oracle firewall: %zu agree with Python, %zu explained divergences\n", agree, diverge);
    CHECK(agree + diverge == 25);
    CHECK(diverge == divergences.size());
}
