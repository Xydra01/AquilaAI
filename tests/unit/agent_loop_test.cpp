#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/orchestrator_module.hpp"
#include "aquila/agent/run_record.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/recipe.hpp"
#include "aquila/types/scratchpad.hpp"
#include "aquila/types/tool_interaction.hpp"

#include "replay_backend.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

#include <cstddef>
#include <cstdint>
#include <set>
#include <string>
#include <thread>
#include <utility>
#include <vector>

using namespace aquila;
using aquila::test::ReplayBackend;
using aquila::test::TempDir;

namespace {

// --- Scripting helpers ------------------------------------------------------

// Build the backend reply string for one turn: the canonical JSON of an
// ActionCall. The AgentLoop parses the backend content with parse<ActionCall>,
// so a canonically-serialized ActionCall is exactly what a "valid" turn looks
// like. `thought` is kept constant so transcripts stay deterministic.
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

// A reply that calls OrchestratorModule.checkpoint_notes. With no required
// fields configured this always succeeds and never completes the recipe, so it
// is the canonical "valid, non-terminal" turn used to count turns.
std::string checkpoint_reply() {
    return action_reply("OrchestratorModule", "checkpoint_notes");
}

// A reply that calls OrchestratorModule.complete_recipe with the given output.
std::string complete_reply(const std::string& output) {
    Json args = Json::object();
    args["output"] = output;
    return action_reply("OrchestratorModule", "complete_recipe", args);
}

// --- Recipe helpers ---------------------------------------------------------

// A minimal recipe loading only the OrchestratorModule, exposing
// checkpoint_notes and complete_recipe, with no required fields and no exit-gate
// hook. The simplest driver for the loop's turn mechanics.
RecipeCartridge orchestrator_only_recipe() {
    RecipeCartridge recipe;
    recipe.recipe_id = "agent_loop_test_orchestrator_only";
    recipe.goal_template = "do the thing";
    ModuleLoad orch;
    orch.module = "OrchestratorModule";
    orch.initial_state = Json::object();  // no required_fields
    orch.expose_actions = {"checkpoint_notes", "trigger_context_condense", "complete_recipe"};
    recipe.load_modules.push_back(std::move(orch));
    return recipe;
}

LoopConfig make_config(std::uint32_t max_turns) {
    LoopConfig config;
    config.system_prompt = "you are a test agent";
    config.task_id = "task-agent-loop";
    config.mode = "test";
    config.instance_id = "inst-1";
    config.tier = RuntimeTierConfig::default_config();
    config.tier.limits.max_turns = max_turns;
    return config;
}

}  // namespace

// ---------------------------------------------------------------------------
// Property 1: One action dispatched per valid turn.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 1: each turn executes exactly one
// execute_action and appends exactly one ToolInteraction to the transcript and
// the rolling tail.
// Validates: Requirements 1.2
TEST_CASE("Property 1: one action dispatched per valid turn", "[rapidcheck][agent_loop]") {
    rc::prop("every valid turn records exactly one ToolInteraction and one generate call", [] {
        // N valid, non-terminal turns (checkpoint_notes always succeeds and never
        // completes). max_turns == N so the loop processes every scripted turn and
        // then terminates on the turn limit.
        const std::uint32_t n = *rc::gen::inRange<std::uint32_t>(1, 8);

        TempDir tmp;
        const RecipeCartridge recipe = orchestrator_only_recipe();
        const LoopConfig config = make_config(n);

        std::vector<GenerationResult> scripted;
        for (std::uint32_t i = 0; i < n; ++i) {
            scripted.push_back(ok_reply(checkpoint_reply()));
        }
        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        // The loop ran all N turns without completing.
        RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        RC_ASSERT(result.transcript.size() == static_cast<std::size_t>(n));
        // One generate() per turn.
        RC_ASSERT(backend.generate_calls() == static_cast<std::size_t>(n));

        // Each parsed turn carries exactly one ToolInteraction.
        std::size_t interactions = 0;
        for (std::size_t i = 0; i < result.transcript.size(); ++i) {
            const TurnRecord& turn = result.transcript[i];
            RC_ASSERT(turn.parsed);
            RC_ASSERT(turn.interaction.has_value());
            RC_ASSERT(turn.index == static_cast<std::uint64_t>(i));
            ++interactions;
        }
        // One ToolInteraction per valid turn.
        RC_ASSERT(interactions == static_cast<std::size_t>(n));
    });
}

// ---------------------------------------------------------------------------
// Property 2: Parse failures never throw and always advance a turn.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 2: a reply failing parse<ActionCall> records
// a TurnRecord{parsed==false}, appends corrective guidance, advances exactly one
// turn, and never throws.
// Validates: Requirements 1.3
TEST_CASE("Property 2: parse failures never throw and advance a turn",
          "[rapidcheck][agent_loop]") {
    rc::prop("each unparseable reply advances one non-parsed turn without throwing", [] {
        // A menu of replies that all fail parse<ActionCall>: bad JSON, an empty
        // object (missing required keys), wrong types, and missing keys.
        const std::vector<std::string> bad_menu = {
            "not json",
            "{}",
            "{\"thought\":1}",
            "{\"thought\":\"t\",\"module\":\"M\"}",            // missing action, args
            "{\"module\":\"M\",\"action\":\"a\",\"args\":{}}",  // missing thought
            "[]",
            "42",
        };

        const std::uint32_t n = *rc::gen::inRange<std::uint32_t>(1, 8);
        std::vector<GenerationResult> scripted;
        scripted.reserve(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            const std::size_t pick = *rc::gen::inRange<std::size_t>(0, bad_menu.size());
            scripted.push_back(ok_reply(bad_menu[pick]));
        }

        TempDir tmp;
        const RecipeCartridge recipe = orchestrator_only_recipe();
        const LoopConfig config = make_config(n);

        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        // run() must not throw on any parse failure.
        const TerminalResult result = loop.run(recipe, "do the thing", config);

        RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        RC_ASSERT(result.success == false);
        // Each bad reply consumed exactly one turn.
        RC_ASSERT(result.transcript.size() == static_cast<std::size_t>(n));
        RC_ASSERT(backend.generate_calls() == static_cast<std::size_t>(n));
        for (const TurnRecord& turn : result.transcript) {
            RC_ASSERT(turn.parsed == false);
            RC_ASSERT(turn.interaction.has_value() == false);  // nothing dispatched
            RC_ASSERT(turn.note.empty() == false);             // corrective guidance recorded
        }
    });
}

// ---------------------------------------------------------------------------
// Property 3: Outcome classification is error_code-driven only.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 3: a failed dispatch yields a non-empty
// error_code and success==false; resolution failures surface unknown_module /
// action_not_exposed and the module's own failure codes, and the loop keeps
// running and records each.
// Validates: Requirements 1.4
TEST_CASE("Property 3: outcome classification is error_code-driven only",
          "[rapidcheck][agent_loop]") {
    rc::prop("each failing dispatch records a non-empty error_code with success==false", [] {
        // Three kinds of failing turn, each with a known error_code:
        //   unknown_module      -> module not loaded
        //   action_not_exposed  -> real module, action not in expose_actions
        //   invalid_args        -> exposed action, args violate its schema
        // The recipe exposes create_file on Workspace (so surgical_edit is
        // loaded-but-not-exposed) and checkpoint_notes on Orchestrator.
        enum class Kind { unknown_module, action_not_exposed, invalid_args };
        const int which = *rc::gen::inRange<int>(0, 3);
        const Kind kind = static_cast<Kind>(which);

        std::string reply;
        std::string expected_code;
        switch (kind) {
        case Kind::unknown_module:
            reply = action_reply("NoSuchModule", "whatever");
            expected_code = "unknown_module";
            break;
        case Kind::action_not_exposed:
            // Workspace loads surgical_edit but the recipe exposes only create_file.
            reply = action_reply("WorkspaceModule", "surgical_edit");
            expected_code = "action_not_exposed";
            break;
        case Kind::invalid_args:
            // create_file is exposed; empty args violate its required keys, so the
            // module itself fails with invalid_args.
            reply = action_reply("WorkspaceModule", "create_file");
            expected_code = "invalid_args";
            break;
        }

        // Build a recipe exposing create_file (Workspace) and checkpoint_notes.
        RecipeCartridge recipe = orchestrator_only_recipe();
        ModuleLoad ws;
        ws.module = "WorkspaceModule";
        ws.initial_state = Json::object();
        ws.expose_actions = {"create_file"};  // deliberately NOT surgical_edit
        recipe.load_modules.push_back(std::move(ws));

        TempDir tmp;
        const LoopConfig config = make_config(1);  // single failing turn

        ReplayBackend backend(std::vector<GenerationResult>{ok_reply(reply)});
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        RC_ASSERT(result.transcript.size() == 1);
        const TurnRecord& turn = result.transcript.front();
        RC_ASSERT(turn.parsed);                       // the reply parsed fine
        RC_ASSERT(turn.interaction.has_value());      // one dispatch recorded
        const ActionResult& ar = turn.interaction->result;
        RC_ASSERT(ar.success == false);
        RC_ASSERT(ar.error_code.empty() == false);    // classification carries a code
        RC_ASSERT(ar.error_code == expected_code);
        // The loop did not succeed and kept running to the turn limit.
        RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        RC_ASSERT(result.success == false);
    });
}

// ---------------------------------------------------------------------------
// Property 4: Turn limit terminates as non-success.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 4: a backend that never completes stops after
// exactly max_turns with TerminalResult{outcome==turn_limit, success==false}.
// Validates: Requirements 1.5
TEST_CASE("Property 4: turn limit terminates as non-success", "[rapidcheck][agent_loop]") {
    rc::prop("the loop stops after exactly max_turns turns with a non-success terminal", [] {
        const std::uint32_t n = *rc::gen::inRange<std::uint32_t>(1, 7);

        TempDir tmp;
        const RecipeCartridge recipe = orchestrator_only_recipe();
        const LoopConfig config = make_config(n);

        // Script exactly N valid, non-completing turns so the loop consumes one
        // per turn and terminates on the turn limit (never calling complete_recipe).
        std::vector<GenerationResult> scripted;
        for (std::uint32_t i = 0; i < n; ++i) {
            scripted.push_back(ok_reply(checkpoint_reply()));
        }
        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        RC_ASSERT(result.success == false);
        // Exactly N turns were processed.
        RC_ASSERT(result.transcript.size() == static_cast<std::size_t>(n));
        RC_ASSERT(backend.generate_calls() == static_cast<std::size_t>(n));
        RC_ASSERT(result.run_record.step_index == static_cast<std::uint64_t>(n));
    });
}

// ---------------------------------------------------------------------------
// Property 5: Determinism — identical inputs yield byte-identical transcripts.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 5: two runs with the same recipe, request and
// replay script produce byte-identical transcripts and run records via canonical
// serialization.
// Validates: Requirements 1.6
TEST_CASE("Property 5: determinism", "[rapidcheck][agent_loop]") {
    rc::prop("two independent runs with identical inputs produce identical results", [] {
        const std::uint32_t n = *rc::gen::inRange<std::uint32_t>(1, 6);
        // Mix of a few valid non-terminal turns, optionally ending in completion.
        const bool complete = *rc::gen::arbitrary<bool>();

        std::vector<std::string> replies;
        for (std::uint32_t i = 0; i < n; ++i) {
            replies.push_back(checkpoint_reply());
        }
        if (complete) {
            replies.push_back(complete_reply("done"));
        }

        const RecipeCartridge recipe = orchestrator_only_recipe();
        // max_turns large enough that completion (if present) terminates the loop;
        // otherwise the loop hits the turn limit after consuming all replies.
        const LoopConfig config = make_config(static_cast<std::uint32_t>(replies.size()));

        const auto run_once = [&]() {
            TempDir tmp;
            std::vector<GenerationResult> scripted;
            for (const std::string& r : replies) {
                scripted.push_back(ok_reply(r));
            }
            ReplayBackend backend(std::move(scripted));
            const ModuleRegistry registry = ModuleRegistry::builtin();
            ModuleContext ctx;
            ctx.workspace_root = tmp.path();
            AgentLoop loop(backend, registry, ctx);
            return loop.run(recipe, "do the thing", config);
        };

        const TerminalResult a = run_once();
        const TerminalResult b = run_once();

        RC_ASSERT(a.outcome == b.outcome);
        RC_ASSERT(a.success == b.success);
        RC_ASSERT(a.completion_output == b.completion_output);
        RC_ASSERT(a.transcript.size() == b.transcript.size());
        RC_ASSERT(a.transcript == b.transcript);  // TurnRecord has operator==
        RC_ASSERT(to_canonical_string(a.run_record) == to_canonical_string(b.run_record));
    });
}

// ---------------------------------------------------------------------------
// Property 15: The exit gate is a deterministic module call, not an LLM turn.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 15: attempting complete_recipe invokes the
// hook module/action exactly once through the registry with NO backend
// generation during the gate.
// Validates: Requirements 5.1
TEST_CASE("Property 15: exit gate is a deterministic module call, not an LLM turn",
          "[rapidcheck][agent_loop]") {
    rc::prop("the completion turn adds exactly one generate call and the gate adds none", [] {
        // A recipe whose exit-gate hook targets OrchestratorModule.checkpoint_notes
        // (a loaded action that is deliberately NOT exposed to the LLM). The hook
        // runs through the registry with empty args; with no required_fields it
        // succeeds, so completion passes. The key observable: the gate issues no
        // generate() call, so generate_calls() equals the number of turns the
        // backend was asked for (here exactly 1), never one more.

        RecipeCartridge recipe = orchestrator_only_recipe();
        // Expose only complete_recipe so the hook action (checkpoint_notes) is a
        // loaded-but-not-exposed action, proving the gate bypasses expose_actions.
        recipe.load_modules.front().expose_actions = {"complete_recipe"};
        ValidationHook hook;
        hook.module = "OrchestratorModule";
        hook.action = "checkpoint_notes";
        hook.must_succeed = true;
        hook.on_failure_instruction = "save your notes";
        recipe.post_llm_validation_hook = hook;

        // Script extra trailing replies that must never be consumed: the loop
        // terminates on turn 0 via the gate, so the backend is asked to generate
        // exactly once regardless of how many replies remain.
        const std::uint32_t trailing = *rc::gen::inRange<std::uint32_t>(0, 5);
        std::vector<GenerationResult> scripted;
        scripted.push_back(ok_reply(complete_reply("all good")));
        for (std::uint32_t i = 0; i < trailing; ++i) {
            scripted.push_back(ok_reply(checkpoint_reply()));
        }

        TempDir tmp;
        const LoopConfig config = make_config(8);
        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        // Completion succeeded (the hook passed).
        RC_ASSERT(result.outcome == LoopOutcome::success);
        RC_ASSERT(result.success);
        RC_ASSERT(result.completion_output == "all good");
        // Exactly one turn ran, so exactly one generate() call. The gate itself
        // added NO generate call (otherwise this would be 2+).
        RC_ASSERT(result.transcript.size() == 1);
        RC_ASSERT(backend.generate_calls() == 1);
    });
}

// ---------------------------------------------------------------------------
// Property 16: Completion succeeds exactly when the gate passes.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 16: completion returns success==true with the
// output exactly when the hook is absent or passes; a failing must_succeed hook
// does not exit and injects on_failure_instruction.
// Validates: Requirements 5.2, 5.3
TEST_CASE("Property 16: completion succeeds exactly when the gate passes",
          "[rapidcheck][agent_loop]") {
    // (a) No hook: a single complete_recipe turn succeeds with the given output.
    rc::prop("no-hook completion succeeds with the completion output", [] {
        TempDir tmp;
        const RecipeCartridge recipe = orchestrator_only_recipe();  // no hook
        const LoopConfig config = make_config(8);

        ReplayBackend backend(std::vector<GenerationResult>{ok_reply(complete_reply("ship it"))});
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        RC_ASSERT(result.outcome == LoopOutcome::success);
        RC_ASSERT(result.success);
        RC_ASSERT(result.completion_output == "ship it");
        RC_ASSERT(result.transcript.size() == 1);
    });

    // (b) must_succeed hook that fails deterministically: completion never
    // succeeds; the loop continues and ends at the turn limit as non-success.
    rc::prop("a failing must_succeed gate never exits and ends at the turn limit", [] {
        const std::uint32_t n = *rc::gen::inRange<std::uint32_t>(1, 6);

        // Load ExecutionModule with no test_cmd; its run_test_suite then fails
        // deterministically with error_code "not_configured" — no process runs.
        RecipeCartridge recipe = orchestrator_only_recipe();
        recipe.load_modules.front().expose_actions = {"complete_recipe"};
        ModuleLoad exec;
        exec.module = "ExecutionModule";
        exec.initial_state = Json::object();  // no test_cmd configured
        exec.expose_actions = {"run_test_suite"};
        recipe.load_modules.push_back(std::move(exec));

        ValidationHook hook;
        hook.module = "ExecutionModule";
        hook.action = "run_test_suite";  // fails: not_configured
        hook.must_succeed = true;
        hook.on_failure_instruction = "the gate failed; keep working";
        recipe.post_llm_validation_hook = hook;

        // Every turn requests completion; the gate always fails, so the loop keeps
        // going until it hits the turn limit.
        std::vector<GenerationResult> scripted;
        for (std::uint32_t i = 0; i < n; ++i) {
            scripted.push_back(ok_reply(complete_reply("attempt")));
        }

        TempDir tmp;
        const LoopConfig config = make_config(n);
        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        // The gate never passed, so the loop never reported success.
        RC_ASSERT(result.success == false);
        RC_ASSERT(result.outcome == LoopOutcome::turn_limit);
        RC_ASSERT(result.transcript.size() == static_cast<std::size_t>(n));
    });
}

// ---------------------------------------------------------------------------
// Property 19: Session fields advance in the run record and never leak into
// memory.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 19: after each turn step_index increments and
// last_interaction updates, and no run-record session field appears in the
// AgentScratchpad.
// Validates: Requirements 6.2
TEST_CASE("Property 19: session fields advance in the run record and never leak into memory",
          "[rapidcheck][agent_loop]") {
    rc::prop("step_index == completed turns, last_interaction matches, key sets are disjoint", [] {
        const std::uint32_t k = *rc::gen::inRange<std::uint32_t>(1, 7);

        TempDir tmp;
        const RecipeCartridge recipe = orchestrator_only_recipe();
        const LoopConfig config = make_config(k);

        std::vector<GenerationResult> scripted;
        for (std::uint32_t i = 0; i < k; ++i) {
            scripted.push_back(ok_reply(checkpoint_reply()));
        }
        ReplayBackend backend(std::move(scripted));
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        AgentLoop loop(backend, registry, ctx);

        const TerminalResult result = loop.run(recipe, "do the thing", config);

        // step_index counts the completed turns.
        RC_ASSERT(result.run_record.step_index == static_cast<std::uint64_t>(k));
        // last_interaction matches the last dispatched turn's interaction.
        RC_ASSERT(result.transcript.size() == static_cast<std::size_t>(k));
        const TurnRecord& last = result.transcript.back();
        RC_ASSERT(last.interaction.has_value());
        RC_ASSERT(result.run_record.last_interaction.has_value());
        RC_ASSERT(result.run_record.last_interaction.value() == last.interaction.value());

        // Session fields (RunRecord) and memory fields (AgentScratchpad) are
        // disjoint at the serialized top level: no session key appears in memory.
        const auto top_keys = [](const auto& value) {
            Json j;
            to_json(j, value);
            std::set<std::string> keys;
            for (const auto& item : j.items()) {
                keys.insert(item.key());
            }
            return keys;
        };
        const std::set<std::string> session_keys = top_keys(result.run_record);
        const std::set<std::string> memory_keys = top_keys(AgentScratchpad{});
        for (const std::string& key : session_keys) {
            RC_ASSERT(memory_keys.find(key) == memory_keys.end());
        }
    });
}

// ---------------------------------------------------------------------------
// Task 8.13 — Unit test: the synchronous single-threaded contract.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Requirement 1.1: the loop runs synchronously on one
// thread with all turn state owned by the frame or the condenser (no async, no
// coroutines). The honest, observable assertion: run() is a blocking call that
// returns a fully-populated TerminalResult on the caller's thread, and every
// backend generate() happened on that same thread.
TEST_CASE("AgentLoop runs synchronously on the calling thread") {
    TempDir tmp;
    const RecipeCartridge recipe = orchestrator_only_recipe();
    const LoopConfig config = make_config(3);

    // A backend that records the thread id each generate() ran on, so we can
    // assert the loop never hopped to a worker thread or coroutine executor.
    class ThreadRecordingBackend final : public IInferenceBackend {
    public:
        explicit ThreadRecordingBackend(std::vector<GenerationResult> scripted)
            : scripted_(std::move(scripted)) {}
        void append(const Message& m) override { context_.push_back(m); }
        [[nodiscard]] std::size_t mark_checkpoint() const override { return context_.size(); }
        void rollback_to(std::size_t checkpoint) override { context_.resize(checkpoint); }
        GenerationResult generate(const GenerationParams&, const TokenCallback&) override {
            generate_threads_.push_back(std::this_thread::get_id());
            const GenerationResult reply = scripted_.at(next_);
            ++next_;
            return reply;
        }
        [[nodiscard]] ComputeProfile active_profile() const noexcept override {
            return ComputeProfile::cpu_low_spec_edge;
        }
        [[nodiscard]] bool supports_kv_reuse() const noexcept override { return false; }
        [[nodiscard]] const std::vector<std::thread::id>& generate_threads() const noexcept {
            return generate_threads_;
        }

    private:
        std::vector<GenerationResult> scripted_;
        std::vector<Message> context_;
        std::vector<std::thread::id> generate_threads_;
        std::size_t next_ = 0;
    };

    std::vector<GenerationResult> scripted;
    scripted.push_back(ok_reply(checkpoint_reply()));
    scripted.push_back(ok_reply(complete_reply("synchronous done")));
    ThreadRecordingBackend backend(std::move(scripted));

    const ModuleRegistry registry = ModuleRegistry::builtin();
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();
    AgentLoop loop(backend, registry, ctx);

    const std::thread::id caller = std::this_thread::get_id();
    // run() blocks until the loop is done and returns a complete result inline.
    const TerminalResult result = loop.run(recipe, "do the thing", config);
    const std::thread::id after = std::this_thread::get_id();

    // The caller's thread is unchanged across the blocking call.
    CHECK(caller == after);

    // The result is fully populated synchronously (completion reached on turn 1).
    CHECK(result.outcome == LoopOutcome::success);
    CHECK(result.success);
    CHECK(result.completion_output == "synchronous done");
    CHECK(result.transcript.size() == 2);
    CHECK(result.run_record.step_index == std::uint64_t{2});

    // Every backend generation ran on the caller's thread: no worker threads,
    // no coroutine executor, no async hop.
    REQUIRE(backend.generate_threads().empty() == false);
    for (const std::thread::id& id : backend.generate_threads()) {
        CHECK(id == caller);
    }
}
