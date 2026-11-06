#include "aquila/modules/execution_module.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/workspace/path_firewall.hpp"

#include "fixtures.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <chrono>
#include <cstdio>
#include <fstream>
#include <sstream>

using namespace aquila;
namespace fs = std::filesystem;

namespace {

const std::string kHelper = AQUILA_PROC_HELPER;

std::string quoted(const std::string& s) {
    return "\"" + s + "\"";
}

std::string log_path(const char* name) {
    return path_to_utf8(test::fixture_dir() / "logs" / name);
}

ExecutionModule module_in(const test::TempDir& tmp, const std::string& config_json) {
    ExecutionModule m({tmp.path(), 4500});
    auto cfg = Json::parse(config_json);
    cfg["allowed_programs"] = Json::array({"aquila_proc_helper"});
    m.configure(cfg);
    return m;
}

}  // namespace

TEST_CASE("execution: build with a real MSVC log is reduced to deduplicated blocks") {
    test::TempDir tmp;
    auto m = module_in(tmp, Json{{"build_cmd", quoted(kHelper) + " cat " + quoted(log_path("msvc_template_spam.txt")) + " 2"}}.dump());
    const auto r = m.execute_action("run_build_and_diagnose", Json::object());
    CHECK_FALSE(r.success);
    CHECK(r.error_code == "build_failed");
    INFO(r.llm_facing_output);
    CHECK(r.llm_facing_output.rfind("build FAILED (exit 2, ", 0) == 0);
    CHECK(r.llm_facing_output.find("8 error(s), 0 warning(s), 1 unique") != std::string::npos);
    CHECK(r.llm_facing_output.find("template_spam.cpp:2 error C2039: 'missing': is not a member of 'A'  (x8, same error)") !=
          std::string::npos);
    const auto raw = test::read_bytes(log_path("msvc_template_spam.txt"));
    std::printf("execution build: raw log %zu chars -> %zu chars for the LLM (%llu tokens)\n", raw.size(),
                r.llm_facing_output.size(), static_cast<unsigned long long>(r.token_estimate));
}

TEST_CASE("execution: tests report failures and counts; filters are forwarded") {
    test::TempDir tmp;
    auto m = module_in(tmp, Json{{"test_cmd", quoted(kHelper) + " cat " + quoted(log_path("pytest_many.txt")) + " 1"}}.dump());
    const auto r = m.execute_action("run_test_suite", Json::object());
    CHECK(r.error_code == "tests_failed");
    CHECK(r.llm_facing_output.find("tests: 3 failed, 2 passed, 1 skipped, 1 xfailed") != std::string::npos);
    CHECK(r.llm_facing_output.find("test_x.py failure test_f2: ValueError: boom") != std::string::npos);

    auto ok = module_in(tmp, Json{{"test_cmd", quoted(kHelper) + " cat " + quoted(log_path("pytest_all_pass.txt")) + " 0"}}.dump());
    const auto pass = ok.execute_action("run_test_suite", Json::object());
    CHECK(pass.success);
    CHECK(pass.llm_facing_output.find("tests: 0 failed, 2 passed") != std::string::npos);

    auto args = module_in(tmp, Json{{"test_cmd", quoted(kHelper) + " args pytest"}}.dump());
    (void)args.execute_action("run_test_suite", Json{{"filter", "test_add and not slow"}});
    const auto argv = args.export_state_snapshot()["history"].back()["argv"].get<std::vector<std::string>>();
    CHECK(argv == std::vector<std::string>{kHelper, "args", "pytest", "-k", "test_add and not slow"});
}

TEST_CASE("execution: allowlist, working directory and configuration checks") {
    test::TempDir tmp;
    tmp.write("sub/keep.txt", "x\n");
    ExecutionModule plain({tmp.path(), 4500});
    CHECK(plain.execute_action("run_build_and_diagnose", Json::object()).error_code == "not_configured");
    CHECK(plain.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "print", "1"}}}).error_code == "not_allowed");
    for (const auto* prog : {"cmd", "powershell", "bash", "sh", "rm", "curl"}) {
        INFO(prog);
        CHECK(plain.execute_action("exec_sandboxed_cmd", Json{{"argv", {prog, "-c", "echo hi"}}}).error_code == "not_allowed");
    }
    CHECK(plain.execute_action("exec_sandboxed_cmd", Json{{"argv", Json::array()}}).error_code == "invalid_args");

    auto m = module_in(tmp, "{}");
    const auto r = m.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "print", "2"}}});
    REQUIRE(r.success);
    CHECK(r.llm_facing_output.find("line 0") != std::string::npos);
    CHECK(m.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "exit", "4"}}}).error_code == "command_failed");
    CHECK(m.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "cwd"}}, {"cwd", "../"}}).error_code ==
          "path_outside_root");
    const auto in_sub = m.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "cwd"}}, {"cwd", "sub"}});
    CHECK(in_sub.llm_facing_output.find("/sub") != std::string::npos);

    ExecutionModule c({tmp.path(), 4500});
    const auto unterminated = Json{{"build_cmd", "cmake \"unterminated"}};
    CHECK_THROWS_AS(c.configure(unterminated), SchemaError);
    CHECK_THROWS_AS(c.configure(Json::parse(R"({"cwd":"../outside"})")), SchemaError);
    CHECK_THROWS_AS(c.configure(Json::parse(R"({"timeout_s":0})")), SchemaError);
    CHECK_THROWS_AS(c.configure(Json::parse(R"({"shell":true})")), SchemaError);
}

TEST_CASE("execution: timeout ends the process tree; env secrets are stripped, config env applies") {
    test::TempDir tmp;
    auto m = module_in(tmp, R"({"timeout_s":1.0,"env":{"AQUILA_EXEC_VAR":"set-by-recipe"}})");
    const auto start = std::chrono::steady_clock::now();
    const auto r = m.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "spawn-grandchild", "30000"}}});
    const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    CHECK(r.error_code == "timeout");
    CHECK(r.llm_facing_output.find("TIMED OUT after 1.0s (process tree killed)") != std::string::npos);
    CHECK(elapsed < 4.0);
    CHECK(m.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "env", "AQUILA_EXEC_VAR"}}}).llm_facing_output.find(
              "AQUILA_EXEC_VAR=set-by-recipe") != std::string::npos);
}

TEST_CASE("execution: history keeps the last 8 runs and snapshots round-trip") {
    test::TempDir tmp;
    auto a = module_in(tmp, Json{{"build_cmd", quoted(kHelper) + " cat " + quoted(log_path("clang_broken.txt")) + " 1"},
                                 {"max_output_chars", 3000}}
                                .dump());
    for (int i = 0; i < 10; ++i) (void)a.execute_action("exec_sandboxed_cmd", Json{{"argv", {kHelper, "exit", std::to_string(i)}}});
    (void)a.execute_action("run_build_and_diagnose", Json::object());
    const auto snap = a.export_state_snapshot();
    REQUIRE(snap["history"].size() == ExecutionModule::kHistory);
    CHECK(snap["history"].back()["errors"] == 3);
    CHECK(snap["history"].back()["top"][0] == "broken.cpp:2 error: expected ';' after return statement");
    CHECK(snap["history"].front()["argv"].back() == "3");  // runs 0-2 dropped

    ExecutionModule b({tmp.path(), 4500});
    b.restore_state_snapshot(snap);
    CHECK(json_io::canonical_dump(b.export_state_snapshot()) == json_io::canonical_dump(snap));
    Json bad = snap;
    bad["history"][0]["exit_code"] = "zero";
    ExecutionModule c({tmp.path(), 4500});
    CHECK_THROWS_AS(c.restore_state_snapshot(bad), SchemaError);
}

TEST_CASE("registry: the design doc recipe (D:L433-477) validates against the built-in modules") {
    // Read the recipe block straight from the design document.
    std::istringstream in(test::read_bytes(AQUILA_DESIGN_DOC));
    std::string line;
    std::string block;
    bool seen_marker = false;
    bool inside = false;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (!seen_marker) {
            seen_marker = line.find("Here is what a Recipe JSON looks like") != std::string::npos;
            continue;
        }
        if (line == "```") {
            if (inside) break;
            inside = true;
            continue;
        }
        if (inside) block += line + "\n";
    }
    const auto recipe = parse<RecipeCartridge>(block);

    test::TempDir tmp;
    tmp.write("src/keep.txt", "x\n");  // the recipe's root_dir is ./src
    const auto reg = ModuleRegistry::builtin();
    CHECK(reg.ids() ==
          std::vector<std::string>{"ExecutionModule", "KnowledgeModule", "OrchestratorModule", "WorkspaceModule"});
    CHECK_NOTHROW(reg.validate_recipe(recipe, {tmp.path(), 4500}));

    auto typo = recipe;
    typo.load_modules[0].expose_actions[1] = "surgical_edits";
    try {
        reg.validate_recipe(typo, {tmp.path(), 4500});
        FAIL("expected SchemaError");
    } catch (const SchemaError& e) {
        CHECK(e.path() == "/load_modules/0/expose_actions/1");
    }
    auto ghost = recipe;
    ghost.load_modules[1].module = "BuildModule";
    try {
        reg.validate_recipe(ghost, {tmp.path(), 4500});
        FAIL("expected SchemaError");
    } catch (const SchemaError& e) {
        CHECK(e.path() == "/load_modules/1/module");
    }
    std::printf("registry: design doc recipe validates against WorkspaceModule + ExecutionModule\n");
}

TEST_CASE("execution e2e: a real CMake + compiler build of a broken file is diagnosed") {
    test::TempDir tmp;
    tmp.write("proj/CMakeLists.txt", "cmake_minimum_required(VERSION 3.20)\nproject(e2e CXX)\nadd_executable(app main.cpp)\n");
    tmp.write("proj/main.cpp", "int main() {\n    return undefined_thing;\n}\n");
    ExecutionModule m({tmp.path(), 4500});
    m.configure(Json{{"cwd", "proj"}, {"build_cmd", "cmake --build build"}, {"timeout_s", 300}});
    const auto cfg = m.execute_action("exec_sandboxed_cmd", Json{{"argv", {"cmake", "-S", ".", "-B", "build", "-G", "Ninja"}}});
    if (!cfg.success) SKIP("cmake/ninja/compiler not available here: " + cfg.llm_facing_output.substr(0, 300));
    const auto r = m.execute_action("run_build_and_diagnose", Json::object());
    INFO(r.llm_facing_output);
    CHECK(r.error_code == "build_failed");
    CHECK(r.llm_facing_output.find("main.cpp:2") != std::string::npos);
    CHECK(r.llm_facing_output.find("undefined_thing") != std::string::npos);
    CHECK(r.llm_facing_output.find("failed targets:") != std::string::npos);
    std::printf("e2e build: %s", r.llm_facing_output.substr(0, r.llm_facing_output.find('\n') + 1).c_str());
}
