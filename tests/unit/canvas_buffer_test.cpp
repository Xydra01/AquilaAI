#include "aquila/canvas/canvas_buffer.hpp"

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

struct Workspace {
    test::TempDir tmp;
    Workspace() {
        tmp.write("lf.txt", "one\ntwo\nthree\n");
        tmp.write("crlf.txt", "one\r\ntwo\r\nthree\r\n");
        tmp.write("bom.txt", "\xEF\xBB\xBFhello\nworld\n");
        tmp.write("mixed.txt", "a\r\nb\nc\r\n");
        tmp.write("latin1.txt", "caf\xE9\n");
        tmp.write("binary.bin", std::string("PK\0\x03", 4));
        tmp.write("nofinal.txt", "x\ny");
        tmp.write(".env", "SECRET=1\n");
    }
    CanvasBuffer buffer() const { return CanvasBuffer(PathFirewall(tmp.path())); }
    std::string bytes(const std::string& rel) const { return test::read_bytes(tmp.path() / rel); }
};

template <class F>
std::string canvas_code(F&& f) {
    try {
        f();
        return "ok";
    } catch (const CanvasError& e) {
        return e.code();
    } catch (const PathDenied& e) {
        return e.code();
    }
}

}  // namespace

TEST_CASE("canvas: open detects line endings, BOM and encoding") {
    Workspace ws;
    auto c = ws.buffer();
    CHECK(c.open("lf.txt").eol == Eol::lf);
    const auto& crlf = c.open("crlf.txt");
    CHECK(crlf.eol == Eol::crlf);
    CHECK(crlf.text() == "one\ntwo\nthree\n");
    const auto& bom = c.open("bom.txt");
    CHECK(bom.bom);
    CHECK(bom.text() == "hello\nworld\n");
    const auto& mixed = c.open("mixed.txt");
    CHECK(mixed.eol == Eol::lf);
    CHECK(mixed.text() == "a\r\nb\nc\r\n");
    CHECK(canvas_code([&] { c.open("latin1.txt"); }) == "unsupported_encoding");
    CHECK(canvas_code([&] { c.open("binary.bin"); }) == "unsupported_encoding");
    CHECK(canvas_code([&] { c.open("missing.txt"); }) == "not_found");
    CHECK(canvas_code([&] { c.open(".env"); }) == "path_blocked");
    CHECK(canvas_code([&] { c.open("../outside.txt"); }) == "path_outside_root");
}

TEST_CASE("canvas: propose leaves disk untouched; accept writes exactly the change") {
    Workspace ws;
    auto c = ws.buffer();
    for (const auto* f : {"lf.txt", "crlf.txt", "bom.txt", "mixed.txt", "nofinal.txt"}) c.open(f);
    const auto before = all_bytes(ws.tmp.path());

    struct Edit {
        const char* path;
        const char* new_text;
        const char* expected_bytes;
    };
    const Edit edits[] = {
        {"lf.txt", "one\nTWO\nthree\n", "one\nTWO\nthree\n"},
        {"crlf.txt", "one\nTWO\nthree\nfour\n", "one\r\nTWO\r\nthree\r\nfour\r\n"},
        {"bom.txt", "hello\nthere\n", "\xEF\xBB\xBFhello\nthere\n"},
        {"mixed.txt", "a\r\nB\nc\r\n", "a\r\nB\nc\r\n"},
        {"nofinal.txt", "x\nY", "x\nY"},
    };
    std::size_t git_checked = 0;
    for (const auto& e : edits) {
        INFO(e.path);
        const auto before_propose = all_bytes(ws.tmp.path());
        const auto id = c.propose(e.path, e.new_text, "agent");
        CHECK(all_bytes(ws.tmp.path()) == before_propose);  // nothing written yet
        const auto disk_patch = c.disk_diff(c.pending().back());
        const auto pre = ws.bytes(e.path);
        c.accept(id);
        CHECK(ws.bytes(e.path) == e.expected_bytes);
        const auto via_git = test::git_apply(e.path, pre, disk_patch);
        INFO(disk_patch);
        REQUIRE(via_git.has_value());
        CHECK(*via_git == ws.bytes(e.path));
        ++git_checked;
    }
    auto after = all_bytes(ws.tmp.path());
    for (const auto& e : edits) after.erase(e.path);
    auto untouched = before;
    for (const auto& e : edits) untouched.erase(e.path);
    CHECK(after == untouched);
    CHECK(c.pending().empty());
    std::printf("canvas accept: %zu edits, git apply reproduced every file; %zu other files byte-identical\n",
                git_checked, untouched.size());
}

TEST_CASE("canvas: stale patches, disk changes and unknown ids are refused") {
    Workspace ws;
    auto c = ws.buffer();
    c.open("lf.txt");
    const auto p1 = c.propose("lf.txt", "one\n", "agent");
    const auto p2 = c.propose("lf.txt", "two\n", "agent");
    c.accept(p1);
    CHECK(canvas_code([&] { c.accept(p2); }) == "stale_patch");
    CHECK(ws.bytes("lf.txt") == "one\n");
    CHECK(canvas_code([&] { c.accept("p99"); }) == "no_such_patch");
    c.reject(p2);
    CHECK(c.pending().empty());

    const auto p3 = c.propose("lf.txt", "three\n", "agent");
    ws.tmp.write("lf.txt", "edited elsewhere\n");
    CHECK(canvas_code([&] { c.accept(p3); }) == "disk_changed");
    CHECK(ws.bytes("lf.txt") == "edited elsewhere\n");
    CHECK(c.find("lf.txt")->current == 1);
    CHECK(c.pending().size() == 1);  // still pending, nothing lost
}

TEST_CASE("canvas: undo, redo and revert write through") {
    Workspace ws;
    auto c = ws.buffer();
    c.open("crlf.txt");
    c.accept(c.propose("crlf.txt", "v1\n", "agent"));
    c.accept(c.propose("crlf.txt", "v2\n", "agent"));
    CHECK(ws.bytes("crlf.txt") == "v2\r\n");
    c.undo("crlf.txt");
    CHECK(ws.bytes("crlf.txt") == "v1\r\n");
    c.redo("crlf.txt");
    CHECK(ws.bytes("crlf.txt") == "v2\r\n");
    CHECK(canvas_code([&] { c.redo("crlf.txt"); }) == "nothing_to_redo");
    c.revert("crlf.txt");
    CHECK(ws.bytes("crlf.txt") == "one\r\ntwo\r\nthree\r\n");
    c.undo("crlf.txt");  // revert is undoable
    CHECK(ws.bytes("crlf.txt") == "v2\r\n");
}

TEST_CASE("canvas: created files are written on accept; existing files cannot be created") {
    Workspace ws;
    auto c = ws.buffer();
    c.create("src/new/mod.py");
    CHECK_FALSE(fs::exists(ws.tmp.path() / "src" / "new" / "mod.py"));
    const auto id = c.propose("src/new/mod.py", "x = 1\n", "agent");
    CHECK(c.pending().back().unified_diff.rfind("--- /dev/null\n+++ b/src/new/mod.py\n", 0) == 0);
    c.accept(id);
    CHECK(ws.bytes("src/new/mod.py") == "x = 1\n");
    CHECK(canvas_code([&] { c.create("lf.txt"); }) == "exists");
    CHECK(canvas_code([&] { c.create("build/x.txt"); }) == "path_blocked");
}

TEST_CASE("canvas: snapshot round-trips and a restored patch still applies") {
    Workspace ws;
    auto a = ws.buffer();
    a.open("lf.txt");
    a.open("crlf.txt");
    a.accept(a.propose("lf.txt", "one\n", "agent"));
    const auto pending_id = a.propose("crlf.txt", "changed\n", "user");
    const auto snap = a.snapshot();

    auto b = ws.buffer();
    b.restore(snap);
    CHECK(json_io::canonical_dump(b.snapshot()) == json_io::canonical_dump(snap));
    b.accept(pending_id);
    CHECK(ws.bytes("crlf.txt") == "changed\r\n");
    b.undo("lf.txt");
    CHECK(ws.bytes("lf.txt") == "one\ntwo\nthree\n");

    Json bad = snap;
    bad["documents"][0]["current"] = 9;
    CHECK_THROWS_AS(ws.buffer().restore(bad), SchemaError);
    bad = snap;
    bad["extra"] = 1;
    CHECK_THROWS_AS(ws.buffer().restore(bad), SchemaError);
}
