#include "aquila/exec/process.hpp"

#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <thread>

#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <csignal>
#include <sys/types.h>
#endif

using namespace aquila;
using aquila::exec::RunOptions;
namespace fs = std::filesystem;

namespace {

const std::string kHelper = AQUILA_PROC_HELPER;

exec::RunResult helper(std::vector<std::string> args, double timeout_s = 20.0, std::size_t cap = 1 << 20) {
    RunOptions o;
    o.argv.push_back(kHelper);
    for (auto& a : args) o.argv.push_back(std::move(a));
    o.timeout_s = timeout_s;
    o.max_output_bytes = cap;
    return exec::run(o);
}

std::string lf(std::string s) {
    std::string out;
    for (std::size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\r' && i + 1 < s.size() && s[i + 1] == '\n') continue;
        out += s[i];
    }
    return out;
}

bool alive(long pid) {
#ifdef _WIN32
    HANDLE h = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, static_cast<DWORD>(pid));
    if (h == nullptr) return false;
    const bool running = WaitForSingleObject(h, 0) == WAIT_TIMEOUT;
    CloseHandle(h);
    return running;
#else
    return ::kill(static_cast<pid_t>(pid), 0) == 0;
#endif
}

bool dies_within(long pid, double seconds) {
    const auto until = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
    while (std::chrono::steady_clock::now() < until) {
        if (!alive(pid)) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    return !alive(pid);
}

long grandchild_pid(const std::string& output) {
    const auto at = output.find("grandchild ");
    REQUIRE(at != std::string::npos);
    return std::atol(output.c_str() + at + 11);
}

void set_env(const char* name, const char* value) {
#ifdef _WIN32
    _putenv_s(name, value ? value : "");
#else
    if (value) setenv(name, value, 1); else unsetenv(name);
#endif
}

}  // namespace

TEST_CASE("split_command: quotes and Windows paths, never a shell") {
    using V = std::vector<std::string>;
    CHECK(exec::split_command("cmake --build ./build --target unit_tests") ==
          V{"cmake", "--build", "./build", "--target", "unit_tests"});
    CHECK(exec::split_command(R"(python -m pytest "tests/test a.py" -k 'x and y')") ==
          V{"python", "-m", "pytest", "tests/test a.py", "-k", "x and y"});
    CHECK(exec::split_command(R"(C:\tools\bin\tool.exe "C:\a b\file.txt" x)") ==
          V{R"(C:\tools\bin\tool.exe)", R"(C:\a b\file.txt)", "x"});
    // Raw strings holding \" stay outside the macros (MSVC's legacy preprocessor mis-lexes them).
    const std::string escaped_quote = R"(tool "C:\dir\" x)";
    CHECK_THROWS_AS(exec::split_command(escaped_quote), std::invalid_argument);  // \" escapes the quote
    const std::string nested = R"(echo "say \"hi\"" a&&b)";
    const auto nested_argv = exec::split_command(nested);
    CHECK(nested_argv == V{"echo", "say \"hi\"", "a&&b"});
    CHECK(exec::split_command(R"(x "" y)") == V{"x", "", "y"});
    CHECK_THROWS_AS(exec::split_command("bad \"quote"), std::invalid_argument);
    CHECK_THROWS_AS(exec::split_command("   "), std::invalid_argument);
}

TEST_CASE("secret environment names") {
    for (const auto* n : {"GITHUB_TOKEN", "OPENAI_API_KEY", "aws_secret_access_key", "DB_PASSWORD", "MY_APIKEY",
                          "GOOGLE_APPLICATION_CREDENTIALS", "SSH_PRIVATE_KEY"}) {
        INFO(n);
        CHECK(exec::is_secret_env_name(n));
    }
    for (const auto* n : {"PATH", "HOME", "CMAKE_BUILD_TYPE", "OLLAMA_MODEL", "TEMP"}) {
        INFO(n);
        CHECK_FALSE(exec::is_secret_env_name(n));
    }
}

TEST_CASE("run: output, exit codes, stderr, argv round-trip, cwd") {
    auto r = helper({"print", "3"});
    REQUIRE(r.started);
    CHECK(r.exit_code == 0);
    CHECK(lf(r.output) == "line 0\nline 1\nline 2\n");
    CHECK_FALSE(r.timed_out);

    CHECK(helper({"exit", "7"}).exit_code == 7);
    r = helper({"stderr"});
    CHECK(r.exit_code == 3);
    CHECK(lf(r.output) == "to stdout\nto stderr\n");

    const std::vector<std::string> tricky = {"plain", "with space", "quote\"inside", "trail\\", "back\\\\slash", "",
                                             "a&b|c", "tab\there"};
    std::vector<std::string> args = {"args"};
    args.insert(args.end(), tricky.begin(), tricky.end());
    r = helper(args);
    std::string expected;
    for (const auto& a : tricky) expected += "[" + a + "]\n";
    CHECK(lf(r.output) == expected);

    test::TempDir tmp;
    RunOptions o;
    o.argv = {kHelper, "cwd"};
    o.cwd = tmp.path();
    r = exec::run(o);
    CHECK(fs::equivalent(fs::path(lf(r.output).substr(0, lf(r.output).size() - 1)), tmp.path()));
}

TEST_CASE("run: secrets are stripped from the inherited environment; overrides apply") {
    set_env("AQUILA_TEST_SECRET_TOKEN", "hunter2");
    set_env("AQUILA_TEST_PLAIN", "visible");
    CHECK(lf(helper({"env", "AQUILA_TEST_SECRET_TOKEN"}).output) == "AQUILA_TEST_SECRET_TOKEN=<unset>\n");
    CHECK(lf(helper({"env", "AQUILA_TEST_PLAIN"}).output) == "AQUILA_TEST_PLAIN=visible\n");
    RunOptions o;
    o.argv = {kHelper, "env", "AQUILA_TEST_OVERRIDE"};
    o.env["AQUILA_TEST_OVERRIDE"] = "from-module";
    CHECK(lf(exec::run(o).output) == "AQUILA_TEST_OVERRIDE=from-module\n");
    set_env("AQUILA_TEST_SECRET_TOKEN", nullptr);
    set_env("AQUILA_TEST_PLAIN", nullptr);
}

TEST_CASE("run: a timeout kills the whole process tree") {
    const auto start = std::chrono::steady_clock::now();
    const auto r = helper({"spawn-grandchild", "30000"}, 1.0);
    const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    REQUIRE(r.started);
    CHECK(r.timed_out);
    CHECK(elapsed < 4.0);
    const long gc = grandchild_pid(r.output);
    CHECK(gc > 0);
    CHECK(dies_within(gc, 3.0));
    std::printf("tree kill: timeout 1.0s, returned after %.2fs, grandchild %ld %s\n", elapsed, gc,
                alive(gc) ? "STILL ALIVE" : "dead");
}

TEST_CASE("run: children left behind by an exited process are ended too") {
    const auto start = std::chrono::steady_clock::now();
    const auto r = helper({"orphan", "30000"}, 20.0);
    const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    CHECK_FALSE(r.timed_out);
    CHECK(r.exit_code == 0);
    CHECK(elapsed < 4.0);
    const long gc = grandchild_pid(r.output);
    CHECK(dies_within(gc, 3.0));
    std::printf("orphan cleanup: returned after %.2fs, grandchild %ld %s\n", elapsed, gc, alive(gc) ? "STILL ALIVE" : "dead");
}

TEST_CASE("run: output beyond the cap keeps head and tail") {
    const auto r = helper({"print", "100000"}, 20.0, 64 * 1024);
    CHECK(r.truncated);
    CHECK(r.total_bytes > 64 * 1024);
    const auto out = lf(r.output);
    CHECK(out.rfind("line 0\nline 1\n", 0) == 0);
    CHECK(out.find("bytes of output omitted") != std::string::npos);
    CHECK(out.size() >= 11);
    CHECK(out.substr(out.size() - 11) == "line 99999\n");
    CHECK(r.output.size() < 70 * 1024);
}

TEST_CASE("run: missing programs do not start") {
    RunOptions opt;
    opt.argv = {"definitely-not-a-program-aquila"};
    opt.timeout_s = 5.0;
    opt.max_output_bytes = 1024;
    const auto r = exec::run(opt);
    CHECK_FALSE(r.started);
    CHECK(r.error.find("program not found") != std::string::npos);
}

#ifdef _WIN32
TEST_CASE("run: .cmd files run via cmd.exe but refuse cmd metacharacters") {
    test::TempDir tmp;
    tmp.write("hello.cmd", "@echo hi %1\r\n");
    const auto script = (tmp.path() / "hello.cmd").string();
    RunOptions opt1;
    opt1.argv = {script, "there"};
    opt1.cwd = tmp.path();
    opt1.timeout_s = 10.0;
    opt1.max_output_bytes = 4096;
    auto r = exec::run(opt1);
    REQUIRE(r.started);
    CHECK(lf(r.output) == "hi there\n");
    for (const auto* bad : {"a&calc", "x|y", "%PATH%", "q\"uote", "car^et"}) {
        INFO(bad);
        RunOptions bad_opt;
        bad_opt.argv = {script, bad};
        bad_opt.cwd = tmp.path();
        bad_opt.timeout_s = 10.0;
        bad_opt.max_output_bytes = 4096;
        r = exec::run(bad_opt);
        CHECK_FALSE(r.started);
        CHECK(r.error.find("cmd.exe would interpret") != std::string::npos);
    }
}
#endif

TEST_CASE("run: stdin_data is piped to child process") {
    RunOptions opt;
    opt.argv = {kHelper, "echo-stdin"};
    opt.stdin_data = "{\"command\":\"test\",\"value\":42}\n";
    opt.timeout_s = 5.0;
    const auto r = exec::run(opt);
    REQUIRE(r.started);
    CHECK(r.exit_code == 0);
    CHECK_FALSE(r.timed_out);
    CHECK(lf(r.output) == "{\"command\":\"test\",\"value\":42}\n");
}
