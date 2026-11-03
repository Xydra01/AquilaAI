#include "aquila/modules/registry.hpp"
#include "aquila/modules/schema_check.hpp"

#include <catch2/catch_test_macros.hpp>

#include <stdexcept>

using namespace aquila;

namespace {

class EchoModule final : public ModuleBase {
public:
    explicit EchoModule(const ModuleContext&) {}
    std::string module_id() const override { return "EchoModule"; }
    std::vector<ActionSchema> get_actions() const override {
        return {{"echo", "Echo text back.",
                 Json::parse(R"({"type":"object","properties":{"text":{"type":"string"},"times":{"type":"integer","minimum":1}},"required":["text"],"additionalProperties":false})")},
                {"noop", "Do nothing.", Json::parse(R"({"type":"object","additionalProperties":false})")}};
    }
    void configure(const Json& initial_state) override {
        json_io::expect_object(initial_state, "");
        json_io::reject_unknown(initial_state, "", {"prefix"});
        if (initial_state.contains("prefix")) prefix_ = json_io::read_string(initial_state["prefix"], "/prefix");
    }
    Json export_state_snapshot() const override { return Json{{"prefix", prefix_}, {"calls", calls_}}; }
    void restore_state_snapshot(const Json& s) override {
        prefix_ = json_io::read_string(json_io::require(s, "", "prefix"), "/prefix");
        calls_ = static_cast<int>(json_io::read_u64(json_io::require(s, "", "calls"), "/calls"));
    }

protected:
    ActionResult run(const std::string& action, const Json& args) override {
        ++calls_;
        if (action == "noop") return ok("");
        std::string out;
        const auto times = args.contains("times") ? args["times"].get<int>() : 1;
        for (int i = 0; i < times; ++i) out += prefix_ + args["text"].get<std::string>();
        return ok(out);
    }

private:
    std::string prefix_;
    int calls_ = 0;
};

ModuleRegistry echo_registry() {
    ModuleRegistry r;
    r.register_module<EchoModule>("EchoModule");
    return r;
}

RecipeCartridge recipe(const std::string& json) {
    return parse<RecipeCartridge>(json);
}

template <class F>
void expect_schema_error(F&& f, const std::string& path, const std::string& reason) {
    try {
        f();
        FAIL("expected SchemaError at " << path);
    } catch (const SchemaError& e) {
        INFO(e.what());
        CHECK(e.path() == path);
        CHECK(std::string(e.what()).find(reason) != std::string::npos);
    }
}

}  // namespace

TEST_CASE("registry creates registered modules and rejects unknown ids") {
    const auto reg = echo_registry();
    CHECK(reg.contains("EchoModule"));
    CHECK(reg.ids() == std::vector<std::string>{"EchoModule"});
    const auto m = reg.create("EchoModule", {});
    REQUIRE(m != nullptr);
    CHECK(m->module_id() == "EchoModule");
    CHECK_THROWS_AS(reg.create("Nope", {}), std::invalid_argument);
}

TEST_CASE("execute_action validates args against the action schema") {
    auto m = echo_registry().create("EchoModule", {});
    const auto good = m->execute_action("echo", Json::parse(R"({"text":"hi","times":2})"));
    CHECK(good.success);
    CHECK(good.llm_facing_output == "hihi");
    CHECK(good.token_estimate == 1);

    const auto unknown = m->execute_action("shout", Json::object());
    CHECK(unknown.error_code == "unknown_action");
    for (const auto& [args, needle] : std::vector<std::pair<std::string, std::string>>{
             {R"({})", "/text: missing required key"},
             {R"({"text":5})", "/text: expected string"},
             {R"({"text":"a","times":0})", "/times: must be >= 1"},
             {R"({"text":"a","loud":true})", "/loud: unknown key"},
             {R"([])", "expected object"}}) {
        INFO(args);
        const auto r = m->execute_action("echo", Json::parse(args));
        CHECK(r.error_code == "invalid_args");
        CHECK(r.llm_facing_output.find(needle) != std::string::npos);
        CHECK(is_valid_error_code(r.error_code));
    }
}

TEST_CASE("snapshot export/restore round-trips module state") {
    const auto reg = echo_registry();
    auto a = reg.create("EchoModule", {});
    a->configure(Json::parse(R"({"prefix":">"})"));
    (void)a->execute_action("noop", Json::object());
    const auto snap = a->export_state_snapshot();
    auto b = reg.create("EchoModule", {});
    b->restore_state_snapshot(snap);
    CHECK(json_io::canonical_dump(b->export_state_snapshot()) == json_io::canonical_dump(snap));
    CHECK(b->execute_action("echo", Json::parse(R"({"text":"x"})")).llm_facing_output == ">x");
}

TEST_CASE("validate_recipe reports the recipe path of every problem") {
    const auto reg = echo_registry();
    const std::string good = R"({"recipe_id":"r","goal_template":"g",
        "load_modules":[{"module":"EchoModule","initial_state":{"prefix":"-"},"expose_actions":["echo","noop"]}],
        "pre_llm_hooks":[{"module":"EchoModule","action":"echo","args":{"text":"{{x}}"}}],
        "post_llm_validation_hook":{"module":"EchoModule","action":"noop","must_succeed":true,"on_failure_instruction":"fix"}})";
    CHECK_NOTHROW(reg.validate_recipe(recipe(good), {}));

    expect_schema_error([&] {
        reg.validate_recipe(recipe(R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"EchoModule","initial_state":{},"expose_actions":["echo","ecko"]}]})"), {});
    }, "/load_modules/0/expose_actions/1", "has no action 'ecko'");

    expect_schema_error([&] {
        reg.validate_recipe(recipe(R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"EchoModule","initial_state":{},"expose_actions":[]},{"module":"Ghost","initial_state":{},"expose_actions":[]}]})"), {});
    }, "/load_modules/1/module", "'Ghost' is not registered");

    expect_schema_error([&] {
        reg.validate_recipe(recipe(R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"EchoModule","initial_state":{"prefx":"-"},"expose_actions":[]}]})"), {});
    }, "/load_modules/0/initial_state/prefx", "unknown key");

    expect_schema_error([&] {
        reg.validate_recipe(recipe(R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"EchoModule","initial_state":{},"expose_actions":[]}],
            "pre_llm_hooks":[{"module":"EchoModule","action":"echo","args":{}}]})"), {});
    }, "/pre_llm_hooks/0/args/text", "missing required key");

    expect_schema_error([&] {
        reg.validate_recipe(recipe(R"({"recipe_id":"r","goal_template":"g","load_modules":[{"module":"EchoModule","initial_state":{},"expose_actions":[]}],
            "post_llm_validation_hook":{"module":"EchoModule","action":"build","must_succeed":true,"on_failure_instruction":""}})"), {});
    }, "/post_llm_validation_hook/action", "has no action 'build'");
}

TEST_CASE("check_schema subset: enum, items, minItems, nested paths") {
    const auto schema = Json::parse(R"({"type":"object","properties":{
        "mode":{"type":"string","enum":["auto","manual"]},
        "argv":{"type":"array","minItems":1,"items":{"type":"string"}}}})");
    CHECK_NOTHROW(check_schema(schema, Json::parse(R"({"mode":"auto","argv":["a"]})")));
    expect_schema_error([&] { check_schema(schema, Json::parse(R"({"mode":"x"})")); }, "/mode", "is not one of");
    expect_schema_error([&] { check_schema(schema, Json::parse(R"({"argv":[]})")); }, "/argv", "at least 1");
    expect_schema_error([&] { check_schema(schema, Json::parse(R"({"argv":["a",2]})")); }, "/argv/1", "expected string");
}
