#include "aquila/json.hpp"
#include "aquila/types/recipe.hpp"

#include <catch2/catch_test_macros.hpp>

#include <map>
#include <optional>
#include <string>

using namespace aquila;

TEST_CASE("RecipeCartridge include roundtrip and validation") {
    RecipeCartridge c;
    c.recipe_id = "child";
    c.goal_template = "Child goal";
    c.load_modules = {
        {"WorkspaceModule", Json{{"root_dir", "."}}, {"create_file"}},
    };
    c.include = {"base_recipe"};

    Json j;
    to_json(j, c);
    CHECK(j.contains("include"));
    CHECK(j["include"] == Json::array({"base_recipe"}));

    RecipeCartridge parsed;
    from_json(j, parsed, "");
    CHECK(parsed == c);
}

TEST_CASE("resolve_includes merges modules, hooks, and checklists") {
    RecipeCartridge base;
    base.recipe_id = "base";
    base.goal_template = "Base goal: {{task}}";
    base.load_modules = {
        {"WorkspaceModule", Json{{"root_dir", "."}}, {"create_file", "read_file"}},
        {"OrchestratorModule", Json{{"required_fields", Json::array({"active_objective"})}}, {"complete_recipe"}},
    };
    base.pre_llm_hooks = {
        {"WorkspaceModule", "list_dir", Json::object()},
    };
    base.scratchpad_checklist = {"Base step 1", "Base step 2"};

    RecipeCartridge derived;
    derived.recipe_id = "derived";
    derived.goal_template = "Derived goal: {{task}}";
    derived.include = {"base"};
    derived.load_modules = {
        {"WorkspaceModule", Json{{"root_dir", "/workspace"}}, {"surgical_edit"}},
        {"ExecutionModule", Json{{"test_cmd", "pytest"}}, {"run_test_suite"}},
    };
    derived.pre_llm_hooks = {
        {"ExecutionModule", "run_test_suite", Json::object()},
    };
    derived.scratchpad_checklist = {"Base step 2", "Derived step 1"};

    std::map<std::string, RecipeCartridge> catalog = {
        {"base", base},
        {"derived", derived},
    };

    auto resolver = [&](const std::string& id) -> std::optional<RecipeCartridge> {
        auto it = catalog.find(id);
        if (it != catalog.end()) return it->second;
        return std::nullopt;
    };

    RecipeCartridge resolved = resolve_includes(derived, resolver);

    CHECK(resolved.recipe_id == "derived");
    CHECK(resolved.goal_template == "Derived goal: {{task}}");
    CHECK(resolved.include.empty());

    // Check modules: WorkspaceModule should have union of actions and derived initial_state
    REQUIRE(resolved.load_modules.size() == 3);
    auto it_ws = std::find_if(resolved.load_modules.begin(), resolved.load_modules.end(),
                              [](const ModuleLoad& m) { return m.module == "WorkspaceModule"; });
    REQUIRE(it_ws != resolved.load_modules.end());
    CHECK(it_ws->initial_state.at("root_dir") == "/workspace");
    CHECK(it_ws->expose_actions == std::vector<std::string>{"create_file", "read_file", "surgical_edit"});

    // Check pre_llm_hooks: base hooks first, then derived hooks
    REQUIRE(resolved.pre_llm_hooks.size() == 2);
    CHECK(resolved.pre_llm_hooks[0].module == "WorkspaceModule");
    CHECK(resolved.pre_llm_hooks[1].module == "ExecutionModule");

    // Check scratchpad_checklist: deduplicated
    CHECK(resolved.scratchpad_checklist ==
          std::vector<std::string>{"Base step 1", "Base step 2", "Derived step 1"});
}

TEST_CASE("resolve_includes detects cyclic includes") {
    RecipeCartridge r1;
    r1.recipe_id = "r1";
    r1.load_modules = {{"OrchestratorModule", Json::object(), {"complete_recipe"}}};
    r1.include = {"r2"};

    RecipeCartridge r2;
    r2.recipe_id = "r2";
    r2.load_modules = {{"OrchestratorModule", Json::object(), {"complete_recipe"}}};
    r2.include = {"r1"};

    std::map<std::string, RecipeCartridge> catalog = {{"r1", r1}, {"r2", r2}};
    auto resolver = [&](const std::string& id) -> std::optional<RecipeCartridge> {
        auto it = catalog.find(id);
        if (it != catalog.end()) return it->second;
        return std::nullopt;
    };

    CHECK_THROWS_AS(resolve_includes(r1, resolver), SchemaError);
}

TEST_CASE("resolve_includes detects missing include reference") {
    RecipeCartridge r;
    r.recipe_id = "leaf";
    r.load_modules = {{"OrchestratorModule", Json::object(), {"complete_recipe"}}};
    r.include = {"non_existent_recipe"};

    auto resolver = [](const std::string&) -> std::optional<RecipeCartridge> {
        return std::nullopt;
    };

    CHECK_THROWS_AS(resolve_includes(r, resolver), SchemaError);
}

