#include "aquila/workspace/path_firewall.hpp"

#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using namespace aquila;
namespace fs = std::filesystem;

namespace {

// "ok" or the PathDenied code.
std::string verdict(const PathFirewall& fw, const std::string& input, Access access = Access::read) {
    try {
        (void)fw.resolve(input, access);
        return "ok";
    } catch (const PathDenied& e) {
        return e.code();
    }
}

struct Case {
    std::string input;
    Access access;
    std::string expected;
};

}  // namespace

TEST_CASE("firewall: containment, escapes and blocked names") {
    test::TempDir tmp;
    tmp.write("ws/src/main.cpp", "int main(){}\n");
    tmp.write("ws/build/out.log", "log\n");
    tmp.write("outside/secret.txt", "s\n");
    const PathFirewall fw(tmp.path() / "ws");
    const auto abs_inside = path_to_utf8(fw.root() / "src" / "main.cpp");
    const auto abs_outside = path_to_utf8(tmp.path() / "outside" / "secret.txt");

    const std::vector<Case> cases = {
        {"src/main.cpp", Access::read, "ok"},
        {"src\\main.cpp", Access::read, "ok"},
        {"./src/./main.cpp", Access::read, "ok"},
        {"src/new_file.cpp", Access::write, "ok"},                 // need not exist
        {"src/deep/new/dir/x.cpp", Access::write, "ok"},
        {"src/../src/main.cpp", Access::read, "ok"},
        {abs_inside, Access::read, "ok"},
        {"../outside/secret.txt", Access::read, "path_outside_root"},
        {"src/../../outside/secret.txt", Access::read, "path_outside_root"},
        {"a/../../x", Access::read, "path_outside_root"},
        {abs_outside, Access::read, "path_outside_root"},
        {"", Access::read, "path_invalid"},
        {std::string("a\0b", 3), Access::read, "path_invalid"},
        {".env", Access::read, "path_blocked"},
        {"config/.env.local", Access::read, "path_blocked"},
        {"certs/server.PEM", Access::read, "path_blocked"},
        {"keys/deploy.key", Access::read, "path_blocked"},
        {"home/id_rsa", Access::read, "path_blocked"},
        {"data/app.sqlite3", Access::read, "path_blocked"},
        {".git/config", Access::read, "path_blocked"},
        {".git/config", Access::write, "path_blocked"},
        {"build/out.log", Access::read, "ok"},                      // reading build output is allowed
        {"build/out.log", Access::write, "path_blocked"},
        {"node_modules/x/index.js", Access::write, "path_blocked"},
        {"pkg/foo.egg-info/PKG-INFO", Access::write, "path_blocked"},
        {".vscode/settings.json", Access::write, "path_blocked"},
        {"src/build.cpp", Access::write, "ok"},                     // a file named like a dir is fine
        {".gitignore", Access::write, "ok"},
        {"logs/run.log", Access::read, "ok"},
        {"naïve/ünïcode ✓.txt", Access::write, "ok"},
#ifdef _WIN32
        {"C:foo", Access::read, "path_invalid"},
        {"\\\\?\\C:\\Windows\\win.ini", Access::read, "path_invalid"},
        {"\\\\server\\share\\x.txt", Access::read, "path_outside_root"},
        {"C:\\Windows\\win.ini", Access::read, "path_outside_root"},
#else
        {"/etc/passwd", Access::read, "path_outside_root"},
#endif
    };
    for (const auto& c : cases) {
        INFO("input: " << c.input << " access: " << (c.access == Access::read ? "read" : "write"));
        CHECK(verdict(fw, c.input, c.access) == c.expected);
    }
    std::printf("firewall: %zu cases\n", cases.size());

    const auto r = fw.resolve("src/main.cpp", Access::read);
    CHECK(r.relative == "src/main.cpp");
    CHECK(fs::exists(r.absolute));
}

#ifdef _WIN32
TEST_CASE("firewall: a differently-cased absolute path inside the root is accepted on Windows") {
    test::TempDir tmp;
    tmp.write("Ws/Src/Main.cpp", "x\n");
    const PathFirewall fw(tmp.path() / "Ws");
    std::string upper = path_to_utf8(fw.root() / "SRC" / "MAIN.CPP");
    for (auto& ch : upper) ch = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
    CHECK(verdict(fw, upper) == "ok");
}
#endif

TEST_CASE("firewall: a link inside the root that points outside is refused") {
    test::TempDir tmp;
    tmp.write("ws/ok.txt", "x\n");
    tmp.write("outside/secret.txt", "s\n");
    const auto link = tmp.path() / "ws" / "escape";
    bool made = false;
#ifdef _WIN32
    const std::string cmd = "cmd /c mklink /J \"" + path_to_utf8(link) + "\" \"" + path_to_utf8(tmp.path() / "outside") + "\" >NUL 2>&1";
    made = std::system(cmd.c_str()) == 0 && fs::exists(link / "secret.txt");
#else
    std::error_code ec;
    fs::create_directory_symlink(tmp.path() / "outside", link, ec);
    made = !ec;
#endif
    if (!made) SKIP("could not create a junction/symlink on this machine");
    const PathFirewall fw(tmp.path() / "ws");
    CHECK(verdict(fw, "escape/secret.txt") == "path_outside_root");
    CHECK(verdict(fw, "escape/new.txt", Access::write) == "path_outside_root");
    CHECK(verdict(fw, "ok.txt") == "ok");
    std::printf("firewall: link escape refused\n");
}

TEST_CASE("firewall: root must be an existing directory") {
    test::TempDir tmp;
    CHECK_THROWS_AS(PathFirewall(tmp.path() / "missing"), std::invalid_argument);
}
