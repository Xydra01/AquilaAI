// recipe_cartridge_test.cpp — M4 tasks 10.2–10.5.
//
// All four tasks live in this single file to avoid cross-file symbol collisions
// with the already-complete agent_loop_test.cpp (which defines its own scripting
// helpers and recipe builders in an anonymous namespace):
//
//   10.2 — Unit test: cartridge load, validation, and JSON parity (Req 7.1, 5.5)
//   10.3 — Property 18: hooks may invoke actions the LLM cannot          (Req 5.5)
//   10.4 — Property 17: invalid hook references fail at load time        (Req 5.4)
//   10.5 — Property 21: a permanently failing gate never reports success (Req 7.4)
//
// The property tests drive the real AgentLoop over the ReplayBackend and a
// per-case temp workspace so the suite stays deterministic and network-free.

#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/module.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/recipe.hpp"

#include "replay_backend.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <ios>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using namespace aquila;
using aquila::test::ReplayBackend;
using aquila::test::TempDir;

namespace {

// --- Scripting helpers ------------------------------------------------------
// Kept local to this translation unit (an anonymous namespace), mirroring the
// style of agent_loop_test.cpp so the two files never clash at link time.

// The canonical JSON of an ActionCall: exactly what a "valid" backend reply is,
// since the loop parses backend content with parse<ActionCall>.
std::string action_reply(const std::string& module, const std::string& action,
                         Json args = Json::object()) {
    ActionCall call;
    call.thought = "t";
    call.module = module;
    call.action = action;
    call.args = std::move(args);
    return to_canonical_string(call);
}

// A scripted ok GenerationResult carrying `content` as the model reply.
GenerationResult ok_reply(std::string content) {
    GenerationResult g;
    g.ok = true;
    g.content = std::move(content);
    return g;
}

// A reply that calls OrchestratorModule.complete_recipe with the given output.
std::string complete_reply(const std::string& output) {
    Json args = Json::object();
    args["output"] = output;
    return action_reply("OrchestratorModule", "complete_recipe", args);
}

LoopConfig make_config(std::uint32_t max_turns) {
    LoopConfig config;
    config.system_prompt = "you are a test agent";
    config.task_id = "task-recipe-cartridge";
    config.mode = "test";
    config.instance_id = "inst-1";
    config.tier = RuntimeTierConfig::default_config();
    config.tier.limits.max_turns = max_turns;
    return config;
}

// A ModuleContext rooted at a temp workspace, as the loop and registry expect.
ModuleContext context_in(const TempDir& tmp) {
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();
    return ctx;
}

// Reads the on-disk recipe JSON exactly (binary) from AQUILA_RECIPE_DIR, the
// compile definition CMake sets to src/core/agent/recipes. The recipe lives
// under src/, not tests/fixtures, so AQUILA_FIXTURE_DIR does not reach it.
std::string read_recipe_file(const std::string& name) {
    const std::string path = std::string(AQUILA_RECIPE_DIR) + "/" + name;
    std::ifstream in(path, std::ios::binary);
    REQUIRE(in.is_open());
    std::ostringstream buf;
    buf << in.rdbuf();
    return buf.str();
}

}  // namespace

// ===========================================================================
// 10.2 — Unit test: cartridge load, validation, and JSON parity (Req 7.1, 5.5).
// ===========================================================================
// Feature: m4-agent-loop, task 10.2: the embedded code_smoke_file recipe parses,
// matches the authoritative on-disk JSON byte-for-byte in both directions,
// passes ModuleRegistry::validate_recipe, and its exit-gate hook names an action
// that is deliberately NOT in that module's expose_actions (allowed for a
// HookCall, Req 5.5).
TEST_CASE("code_smoke_file cartridge loads, validates, and matches its JSON") {
    const RecipeCartridge recipe = code_smoke_file_recipe();
    const std::string on_disk = read_recipe_file("code_smoke_file.recipe.json");

    SECTION("JSON parity in both directions (Req 7.1)") {
        // Serializing the accessor's value reproduces the on-disk bytes exactly.
        CHECK(to_canonical_string(recipe) == on_disk);
        // Parsing the on-disk bytes reproduces the accessor's value exactly.
        CHECK(parse<RecipeCartridge>(on_disk) == recipe);
    }

    SECTION("validate_recipe accepts the cartridge (Req 7.1)") {
        TempDir tmp;
        const ModuleRegistry registry = ModuleRegistry::builtin();
        const ModuleContext ctx = context_in(tmp);
        // A valid cartridge validates without throwing.
        CHECK_NOTHROW(registry.validate_recipe(recipe, ctx));
    }

    SECTION("the exit-gate hook targets an action outside expose_actions (Req 5.5)") {
        // The recipe's post_llm_validation_hook runs ExecutionModule.run_test_suite.
        REQUIRE(recipe.post_llm_validation_hook.has_value());
        const ValidationHook& hook = *recipe.post_llm_validation_hook;
        CHECK(hook.module == "ExecutionModule");
        CHECK(hook.action == "run_test_suite");

        // Find ExecutionModule's load entry and confirm run_test_suite is NOT in
        // its expose_actions — so the LLM cannot call it, but the HookCall can.
        bool found_exec = false;
        for (const ModuleLoad& load : recipe.load_modules) {
            if (load.module != hook.module) {
                continue;
            }
            found_exec = true;
            const bool hook_action_exposed =
                std::find(load.expose_actions.begin(), load.expose_actions.end(), hook.action) !=
                load.expose_actions.end();
            CHECK(hook_action_exposed == false);
        }
        CHECK(found_exec);

        // run_test_suite is nonetheless a real action the loaded module provides,
        // which is why a HookCall can invoke it even though it is unexposed.
        TempDir tmp;
        const ModuleRegistry registry = ModuleRegistry::builtin();
        auto exec = registry.create("ExecutionModule", context_in(tmp));
        bool module_has_action = false;
        for (const ActionSchema& schema : exec->get_actions()) {
            if (schema.action_name == hook.action) {
                module_has_action = true;
            }
        }
        CHECK(module_has_action);
    }
}

// ===========================================================================
// 10.3 — Property 18: Hooks may invoke actions the LLM cannot (Req 5.5).
// ===========================================================================
// Feature: m4-agent-loop, Property 18: for any action present on a loaded module
// but absent from its expose_actions, a HookCall invokes it successfully while an
// LLM-driven dispatch of the same action is rejected with
// error_code == "action_not_exposed".
// Validates: Requirements 5.5
TEST_CASE("Property 18: hooks may invoke actions the LLM cannot",
          "[rapidcheck][recipe]") {
    rc::prop("an unexposed action is rejected for the LLM yet runnable by the exit-gate hook", [] {
        // The loaded-but-not-exposed action to probe. Each is a real
        // OrchestratorModule action that, invoked by a HookCall with empty args
        // (no required_fields configured), succeeds — so the exit gate passes.
        // The LLM may call ONLY complete_recipe, so dispatching any of these
        // directly must be rejected with action_not_exposed.
        const std::vector<std::string> unexposed_menu = {
            "checkpoint_notes",
            "trigger_context_condense",
        };
        const std::size_t pick = *rc::gen::inRange<std::size_t>(0, unexposed_menu.size());
        const std::string hidden_action = unexposed_menu[pick];

        // A recipe loading only the OrchestratorModule and exposing ONLY
        // complete_recipe, so `hidden_action` is loaded but not exposed. The
        // exit-gate hook targets `hidden_action` (a HookCall, so expose_actions is
        // not consulted).
        RecipeCartridge recipe;
        recipe.recipe_id = "p18_recipe";
        recipe.goal_template = "do the thing";
        ModuleLoad orch;
        orch.module = "OrchestratorModule";
        orch.initial_state = Json::object();  // no required_fields -> actions succeed
        orch.expose_actions = {"complete_recipe"};
        recipe.load_modules.push_back(std::move(orch));
        ValidationHook hook;
        hook.module = "OrchestratorModule";
        hook.action = hidden_action;
        hook.must_succeed = true;
        hook.on_failure_instruction = "save your notes";
        recipe.post_llm_validation_hook = hook;

        const ModuleRegistry registry = ModuleRegistry::builtin();

        // (a) LLM path: a single turn whose ActionCall dispatches `hidden_action`
        // directly. The loop must reject it with error_code == "action_not_exposed"
        // and keep running (never succeeding) to the turn limit.
        {
            TempDir tmp;
            const LoopConfig config = make_config(1);
            ReplayBackend backend(
                std::vector<GenerationResult>{ok_reply(action_reply("OrchestratorModule", hidden_action))});
            AgentLoop loop(backend, registry, context_in(tmp));

            const TerminalResult result = loop.run(recipe, "do the thing", config);

            RC_ASSERT(result.transcript.size() == 1);
            const TurnRecord& turn = result.transcript.front();
            RC_ASSERT(turn.parsed);
            RC_ASSERT(turn.interaction.has_value());
            const ActionResult& ar = turn.interaction->result;
            RC_ASSERT(ar.success == false);
            RC_ASSERT(ar.error_code == "action_not_exposed");
            RC_ASSERT(result.success == false);
            RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        }

        // (b) Hook path: the LLM calls the exposed complete_recipe, which triggers
        // the deterministic exit gate. The gate runs the SAME `hidden_action` as a
        // HookCall — bypassing expose_actions — and it succeeds, so completion
        // succeeds. This proves the hook invoked the action the LLM could not.
        {
            TempDir tmp;
            const LoopConfig config = make_config(4);
            std::vector<GenerationResult> scripted;
            scripted.push_back(ok_reply(complete_reply("all good")));
            ReplayBackend backend(std::move(scripted));
            AgentLoop loop(backend, registry, context_in(tmp));

            const TerminalResult result = loop.run(recipe, "do the thing", config);

            RC_ASSERT(result.outcome == LoopOutcome::success);
            RC_ASSERT(result.success);
            RC_ASSERT(result.completion_output == "all good");
            // Exactly one turn ran (the completion turn); the gate added no turn.
            RC_ASSERT(result.transcript.size() == 1);
        }
    });
}

// ===========================================================================
// 10.4 — Property 17: Invalid hook references fail at load time (Req 5.4).
// ===========================================================================
// Feature: m4-agent-loop, Property 17: for any recipe whose post_llm_validation_hook
// names a module not in load_modules, or an action no loaded module exposes for
// hooks, loading the recipe throws SchemaError with a non-empty JSON-pointer path;
// a structurally valid recipe does not throw.
// Validates: Requirements 5.4
TEST_CASE("Property 17: invalid hook references fail at load time",
          "[rapidcheck][recipe]") {
    rc::prop("a bad hook module or action throws SchemaError with a non-empty path", [] {
        // Two bad-reference flavors:
        //   bad_module -> hook.module names a module not in load_modules
        //   bad_action -> hook.module is loaded but hook.action is not a real action
        enum class Bad { bad_module, bad_action };
        const Bad flavor =
            *rc::gen::elementOf(std::vector<Bad>{Bad::bad_module, Bad::bad_action});

        // Base recipe: a single loaded OrchestratorModule (a real, registered
        // module), structurally valid apart from the hook we are about to corrupt.
        RecipeCartridge recipe;
        recipe.recipe_id = "p17_recipe";
        recipe.goal_template = "do the thing";
        ModuleLoad orch;
        orch.module = "OrchestratorModule";
        orch.initial_state = Json::object();
        orch.expose_actions = {"complete_recipe"};
        recipe.load_modules.push_back(std::move(orch));

        ValidationHook hook;
        hook.must_succeed = true;
        hook.on_failure_instruction = "retry";
        switch (flavor) {
        case Bad::bad_module:
            // A module id that is NOT present in load_modules (and need not be a
            // registered id at all — it simply is not one the recipe loaded).
            hook.module = *rc::gen::elementOf(
                std::vector<std::string>{"NoSuchModule", "GhostModule", "WorkspaceModule"});
            hook.action = "complete_recipe";
            break;
        case Bad::bad_action:
            // A loaded module, but an action it does not provide for hooks.
            hook.module = "OrchestratorModule";
            hook.action = *rc::gen::elementOf(
                std::vector<std::string>{"no_such_action", "frobnicate", "run_test_suite"});
            break;
        }
        recipe.post_llm_validation_hook = hook;

        TempDir tmp;
        const ModuleRegistry registry = ModuleRegistry::builtin();
        const ModuleContext ctx = context_in(tmp);

        // Loading the recipe (validate_recipe) must throw SchemaError with a
        // non-empty JSON-pointer path pointing at the offending hook.
        bool threw_schema_error = false;
        try {
            registry.validate_recipe(recipe, ctx);
        } catch (const SchemaError& e) {
            threw_schema_error = true;
            RC_ASSERT(e.path().empty() == false);
        }
        RC_ASSERT(threw_schema_error);
    });

    // A structurally valid recipe (the real code_smoke_file cartridge) must NOT
    // throw, confirming the rejection is specific to the bad reference.
    rc::prop("a structurally valid recipe does not throw at load time", [] {
        TempDir tmp;
        const ModuleRegistry registry = ModuleRegistry::builtin();
        const ModuleContext ctx = context_in(tmp);
        const RecipeCartridge recipe = code_smoke_file_recipe();
        bool threw = false;
        try {
            registry.validate_recipe(recipe, ctx);
        } catch (const SchemaError&) {
            threw = true;
        }
        RC_ASSERT(threw == false);
    });
}

// ===========================================================================
// 10.5 — Property 21: A permanently failing gate never reports success (Req 7.4).
// ===========================================================================
// Feature: m4-agent-loop, Property 21: for any forced-failure scenario in which
// the validation hook can never pass, the loop never returns a success terminal
// and ends with TerminalResult{outcome == turn_limit, success == false}.
// Validates: Requirements 7.4
TEST_CASE("Property 21: a permanently failing gate never reports success",
          "[rapidcheck][recipe]") {
    rc::prop("a must_succeed hook that always fails ends at the turn limit as non-success", [] {
        const std::uint32_t n = *rc::gen::inRange<std::uint32_t>(1, 8);

        // A recipe whose exit gate can NEVER pass: ExecutionModule with no test_cmd
        // configured, so run_test_suite fails deterministically with
        // error_code "not_configured" on every attempt — no process ever runs.
        RecipeCartridge recipe;
        recipe.recipe_id = "p21_recipe";
        recipe.goal_template = "do the thing";
        ModuleLoad orch;
        orch.module = "OrchestratorModule";
        orch.initial_state = Json::object();  // no required_fields
        orch.expose_actions = {"complete_recipe"};
        recipe.load_modules.push_back(std::move(orch));
        ModuleLoad exec;
        exec.module = "ExecutionModule";
        exec.initial_state = Json::object();  // NO test_cmd -> run_test_suite fails
        exec.expose_actions = {};             // never exposed to the LLM
        recipe.load_modules.push_back(std::move(exec));

        ValidationHook hook;
        hook.module = "ExecutionModule";
        hook.action = "run_test_suite";
        hook.must_succeed = true;  // a hard gate that must pass to complete
        hook.on_failure_instruction = "the gate failed; keep working";
        recipe.post_llm_validation_hook = hook;

        // Every turn requests completion; the gate fails every time, so the loop
        // can never exit via the gate and runs until the turn limit for any N.
        std::vector<GenerationResult> scripted;
        scripted.reserve(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            scripted.push_back(ok_reply(complete_reply("attempt")));
        }

        TempDir tmp;
        const LoopConfig config = make_config(n);
        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        AgentLoop loop(backend, registry, context_in(tmp));

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        // The gate never passed, so success was never reported; the loop ended on
        // the turn limit after processing every scripted turn.
        RC_ASSERT(result.success == false);
        RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        RC_ASSERT(result.completion_output.empty());
        RC_ASSERT(result.transcript.size() == static_cast<std::size_t>(n));
    });
}
