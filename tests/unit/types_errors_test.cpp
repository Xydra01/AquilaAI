#include "fixtures.hpp"

#include <catch2/catch_test_macros.hpp>

#include <string>

using namespace aquila;

namespace {

// Parsing `text` as T must throw SchemaError at exactly `path`, with `reason` in what().
template <class T>
void expect_error(std::string_view text, const std::string& path, const std::string& reason) {
    INFO("input: " << text);
    try {
        (void)parse<T>(text);
        FAIL("expected SchemaError at '" << path << "'");
    } catch (const SchemaError& e) {
        INFO("what: " << e.what());
        CHECK(e.path() == path);
        CHECK(std::string(e.what()).find(reason) != std::string::npos);
    }
}

const char* const kRecipeHead =
    R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"WorkspaceModule","initial_state":{},"expose_actions":[]}])";

std::string recipe_with(const std::string& tail) {
    return std::string(kRecipeHead) + tail + "}";
}

}  // namespace

TEST_CASE("unknown keys are rejected with their path") {
    expect_error<RecipeCartridge>(
        R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"M","initial_state":{},"expose_action":[]}]})",
        "/load_modules/0/expose_action", "unknown key");
    expect_error<Message>(R"({"role":"user","content":"x","thinking":"y"})", "/thinking", "unknown key");
    expect_error<Message>(R"({"role":"user","content":"x","a/b~c":1})", "/a~1b~0c", "unknown key");
}

TEST_CASE("missing required keys are rejected") {
    expect_error<ActionResult>(R"({"success":true,"error_code":"","llm_facing_output":""})",
                               "/token_estimate", "missing required key");
    expect_error<ActionResult>(R"({"success":true,"llm_facing_output":"","token_estimate":1})",
                               "/error_code", "missing required key");
    expect_error<AgentScratchpad>(R"({"active_objective":""})", "/current_hypothesis",
                                  "missing required key");
    expect_error<RecipeCartridge>(R"({"recipe_id":"r","goal_template":"g"})", "/load_modules",
                                  "missing required key");
}

TEST_CASE("wrong types are rejected") {
    expect_error<Message>(R"({"role":"user","content":5})", "/content", "expected string, got number");
    expect_error<Message>(R"({"role":"user","content":"x","images":"a"})", "/images", "expected array");
    expect_error<Message>(R"({"role":"user","content":"x","images":["a",1]})", "/images/1",
                          "expected string");
    expect_error<ActionResult>(
        R"({"success":"yes","error_code":"","llm_facing_output":"","token_estimate":1})", "/success",
        "expected boolean");
    expect_error<ActionResult>(
        R"({"success":false,"error_code":7,"llm_facing_output":"","token_estimate":1})",
        "/error_code", "expected string");
    expect_error<Message>("[]", "", "expected object, got array");
}

TEST_CASE("bad enum values are rejected") {
    expect_error<Message>(R"({"role":"admin","content":""})", "/role", "unknown role 'admin'");
    expect_error<AgentScratchpad>(
        R"({"active_objective":"","current_hypothesis":"","verified_facts":[],"failed_approaches_do_not_repeat":[],"next_immediate_action":"","checklist":[{"id":"c","text":"t","status":"finished"}]})",
        "/checklist/0/status", "unknown status 'finished'");
}

TEST_CASE("token_estimate must be a non-negative integer") {
    expect_error<ActionResult>(
        R"({"success":true,"error_code":"","llm_facing_output":"","token_estimate":-1})",
        "/token_estimate", "got negative");
    expect_error<ActionResult>(
        R"({"success":true,"error_code":"","llm_facing_output":"","token_estimate":1.5})",
        "/token_estimate", "got number");
}

TEST_CASE("error_code is set exactly when success is false, in snake_case") {
    expect_error<ActionResult>(
        R"({"success":true,"error_code":"os_block","llm_facing_output":"","token_estimate":0})",
        "/error_code", "must be empty when success is true");
    expect_error<ActionResult>(
        R"({"success":false,"error_code":"","llm_facing_output":"","token_estimate":0})",
        "/error_code", "must be set when success is false");
    for (const auto* bad : {"OS_BLOCK", "os block", "1st", "_x", "os-block", "\u00e9"}) {
        INFO(bad);
        CHECK_FALSE(is_valid_error_code(bad));
    }
    expect_error<ActionResult>(
        R"({"success":false,"error_code":"OS BLOCK","llm_facing_output":"","token_estimate":0})",
        "/error_code", "must be snake_case");
    CHECK(is_valid_error_code("write_files_failed"));
    CHECK(is_valid_error_code("e2"));
}

TEST_CASE("free-form args must be objects") {
    expect_error<ActionCall>(R"({"thought":"","module":"M","action":"a","args":[]})", "/args",
                             "expected object, got array");
    expect_error<ActionSchema>(R"({"action_name":"a","description":"","parameters_json_schema":true})",
                               "/parameters_json_schema", "expected object, got boolean");
}

TEST_CASE("recipe semantic rules") {
    expect_error<RecipeCartridge>(
        recipe_with(R"(,"pre_llm_hooks":[{"module":"ExecutionModule","action":"x","args":{}}])"),
        "/pre_llm_hooks/0/module", "module 'ExecutionModule' is not in load_modules");
    expect_error<RecipeCartridge>(
        recipe_with(
            R"(,"post_llm_validation_hook":{"module":"Nope","action":"x","must_succeed":true,"on_failure_instruction":""})"),
        "/post_llm_validation_hook/module", "module 'Nope' is not in load_modules");
    expect_error<RecipeCartridge>(R"({"recipe_id":"r","goal_template":"g","load_modules":[]})",
                                  "/load_modules", "at least one module");
    expect_error<RecipeCartridge>(
        R"({"recipe_id":"","goal_template":"g","load_modules":[{"module":"M","initial_state":{},"expose_actions":[]}]})",
        "/recipe_id", "must not be empty");
}

TEST_CASE("malformed JSON, duplicate keys and bad UTF-8 are rejected") {
    expect_error<Message>(R"({"role":"user","content":)", "", "invalid JSON");
    expect_error<Message>(R"({"role":"user","role":"system","content":""})", "", "duplicate key 'role'");
    expect_error<ActionCall>(R"({"thought":"","module":"M","action":"a","args":{"k":1,"k":2}})", "",
                             "duplicate key 'k'");
    expect_error<Message>("{\"role\":\"user\",\"content\":\"\xff\"}", "", "invalid JSON");

    try {
        (void)to_canonical_string(Message{Role::user, "bad \xff byte", {}});
        FAIL("expected SchemaError on dump");
    } catch (const SchemaError& e) {
        CHECK(e.path().empty());
        CHECK(std::string(e.what()).find("cannot serialize") != std::string::npos);
    }
}

TEST_CASE("same key name in sibling objects is not a duplicate") {
    CHECK_NOTHROW(parse<ActionCall>(
        R"({"thought":"","module":"M","action":"a","args":{"x":{"k":1},"y":{"k":2}}})"));
}
