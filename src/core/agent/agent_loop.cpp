#include "aquila/agent/agent_loop.hpp"

#include "aquila/json.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace aquila {

AgentLoop::AgentLoop(IInferenceBackend& backend, const ModuleRegistry& registry,
                     ModuleContext module_ctx)
    : backend_(backend), registry_(registry), module_ctx_(std::move(module_ctx)) {}

Json AgentLoop::action_call_schema() {
    // The OutputConstraint::json_schema the backend enforces (R14). Mirrors M1
    // ActionCall exactly: all four fields required, no extra keys permitted.
    Json schema = Json::object();
    schema["type"] = "object";

    Json properties = Json::object();
    Json thought = Json::object();
    thought["type"] = "string";
    properties["thought"] = std::move(thought);
    Json module = Json::object();
    module["type"] = "string";
    properties["module"] = std::move(module);
    Json action = Json::object();
    action["type"] = "string";
    properties["action"] = std::move(action);
    Json args = Json::object();
    args["type"] = "object";
    properties["args"] = std::move(args);
    schema["properties"] = std::move(properties);

    schema["required"] = Json::array({"thought", "module", "action", "args"});
    schema["additionalProperties"] = false;
    return schema;
}

GenerationParams AgentLoop::generation_params(const TierLimits& limits) const {
    GenerationParams params;
    // The loop is deterministic (Req 1.6): pin a greedy temperature so an
    // identical replayed context yields an identical reply.
    params.temperature = 0.0;
    // Output budget derived from the tier's thought cap (R14). The reply carries
    // the `thought` (bounded by max_thought_tokens) plus the small {module,
    // action, args} JSON envelope; budget a 4x multiple of the thought cap so the
    // structural overhead and argument payload fit without clipping the schema.
    params.max_tokens = static_cast<std::uint32_t>(limits.max_thought_tokens * 4U);
    params.constraint = OutputConstraint::json_schema(action_call_schema());
    return params;
}

TerminalResult AgentLoop::run(const RecipeCartridge& recipe, const std::string& user_request,
                              const LoopConfig& config) {
    const TierLimits& limits = config.tier.limits;

    // Load-time validation (Req 5.4): a structurally invalid recipe — an unknown
    // module, an unexposed/undeclared action, a bad hook, or an initial_state that
    // configure() rejects — throws SchemaError here, before any turn runs.
    registry_.validate_recipe(recipe, module_ctx_);

    // Build the module set: instantiate each loaded module through the registry
    // (held as unique_ptr, no raw owning pointers) and apply its initial_state.
    std::vector<std::unique_ptr<IAgentModule>> modules;
    modules.reserve(recipe.load_modules.size());
    for (const ModuleLoad& load : recipe.load_modules) {
        std::unique_ptr<IAgentModule> module = registry_.create(load.module, module_ctx_);
        module->configure(load.initial_state);
        modules.push_back(std::move(module));
    }

    // Locate the OrchestratorModule, if the recipe loaded one. The host-facing API
    // (take_intent(), scratchpad(), scratchpad_valid(), completion_output()) lives
    // on the derived type, not IAgentModule, so we down-cast once and keep a
    // non-owning observer pointer — ownership stays in the unique_ptr above (R1
    // forbids raw owning pointers, not observers). A recipe need not load the
    // Orchestrator; `orchestrator == nullptr` means no intent handling and no
    // scratchpad anchoring, handled gracefully below.
    OrchestratorModule* orchestrator = nullptr;
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        if (auto* casted = dynamic_cast<OrchestratorModule*>(module.get()); casted != nullptr) {
            orchestrator = casted;
            break;
        }
    }

    // Seed the condenser from the active tier (Req 2.1): the pinned prefix carries
    // the system prompt and the rendered action-call schema that constrains every
    // reply, so it is the natural recipe schema text to pin.
    ContextCondenser condenser(limits, config.context_strategy);
    condenser.set_pinned_prefix(config.system_prompt,
                                json_io::canonical_dump(action_call_schema()));

    // Open the rolling tail with the user's request so the first turn has context.
    condenser.push_guidance(user_request);

    // Precompute the deterministic generation parameters the turn cycle uses (R14)
    // and capture the backend's starting context position. Because the Ollama
    // scaffold has no KV reuse (supports_kv_reuse() == false), each turn rolls back
    // to this baseline and resends the full context (M2 scaffold).
    const GenerationParams params = generation_params(limits);
    const std::size_t context_baseline = backend_.mark_checkpoint();

    // One RunRecord per run (Req 6.1); starts fresh, never imported (Req 6.3).
    RunRecord run_record;
    run_record.task_id = config.task_id;
    run_record.mode = config.mode;
    run_record.instance_id = config.instance_id;
    run_record.step_index = 0;
    run_record.ground_truth = config.ground_truth;

    TerminalResult result;

    // The deterministic turn cycle (Req 1.2-1.4). Each iteration builds the prompt,
    // regenerates against the full context, parses the reply, resolves and
    // dispatches exactly one action, and records the turn. Ids and any generated
    // text are derived from the turn index only — no clocks, no randomness (Req
    // 1.6). The loop is bounded here by the tier's turn cap; TODO(8.3) replaces
    // this bound with the orchestrator-intent handling, the should_condense() wipe,
    // and the turn-limit terminal semantics.
    for (std::uint64_t turn = 0; turn < limits.max_turns; ++turn) {
        // 1. Assemble the prompt and resend it in full. The scaffold cannot reuse
        // KV, so rewind to the load-time baseline and re-append every message.
        const std::vector<Message> messages = condenser.build_messages();
        backend_.rollback_to(context_baseline);
        for (const Message& message : messages) {
            backend_.append(message);
        }

        // 2. Generate. No streaming: pass an empty TokenCallback. A backend failure
        // (ok == false) is a failed turn — record the backend error, nudge the
        // model, and continue without throwing (Req 1.2).
        const GenerationResult gen = backend_.generate(params, TokenCallback{});
        if (!gen.ok) {
            const std::string note =
                "backend generation failed (" + gen.error_code + ": " + gen.error_detail +
                "); the previous attempt produced no usable reply, try again.";
            TurnRecord record;
            record.index = turn;
            record.raw_reply = gen.content;
            record.parsed = false;
            record.note = note;
            result.transcript.push_back(std::move(record));
            condenser.push_guidance(note);
            continue;
        }

        // 3. Parse the reply as an ActionCall. A malformed reply (syntax error or a
        // schema violation) surfaces as a SchemaError — never let it escape the
        // loop (Req 1.3). Record the failed turn, push a corrective that restates
        // the required schema, and advance one turn.
        ActionCall call;
        try {
            call = parse<ActionCall>(gen.content);
        } catch (const SchemaError&) {
            const std::string note =
                "reply was not a valid action call; respond with a single JSON object "
                "{\"thought\", \"module\", \"action\", \"args\"} and nothing else.";
            TurnRecord record;
            record.index = turn;
            record.raw_reply = gen.content;
            record.parsed = false;
            record.note = note;
            result.transcript.push_back(std::move(record));
            condenser.push_guidance(note);
            continue;
        }

        // 4. Resolve the module/action and dispatch exactly one execute_action,
        // surfacing resolution failures (unknown_module, action_not_exposed) and
        // the module's own failures (unknown_action, invalid_args) as-is. All
        // control flow below branches on success/error_code only (Req 1.4, R19).
        const ActionResult action_result = resolve_and_dispatch(modules, recipe, call);

        // 5. Wrap the outcome as a ToolInteraction with a turn-derived id (Req 1.6),
        // record the cycle in the condenser's rolling tail, and append the turn to
        // the transcript.
        ToolInteraction interaction;
        interaction.id = "t" + std::to_string(turn);
        interaction.module = call.module;
        interaction.action = call.action;
        interaction.args = call.args;
        interaction.result = action_result;
        condenser.record_tool_cycle(interaction);

        TurnRecord record;
        record.index = turn;
        record.raw_reply = gen.content;
        record.parsed = true;
        record.call = call;
        record.interaction = interaction;
        result.transcript.push_back(std::move(record));

        // 6. Advance the RunRecord (Req 6.2): step_index counts completed turns and
        // last_interaction tracks the most recent dispatch. No session field is
        // ever copied into the scratchpad (D12).
        run_record.step_index = turn + 1;
        run_record.last_interaction = std::move(interaction);

        // 7. Re-anchor the scratchpad into the condenser (Req 6/R6 anchored block).
        // The dispatch above may have mutated the Orchestrator's scratchpad (e.g.
        // checkpoint_notes) or any module's state, so — once per turn after the
        // dispatch — refresh the anchored block from the latest scratchpad plus a
        // snapshot of every loaded module. Snapshot order follows the modules
        // vector (deterministic, Req 1.6). Skipped when no Orchestrator is loaded:
        // there is no scratchpad to anchor. This also makes condense()'s
        // "refresh from the latest set_anchored inputs" meaningful on a wipe.
        if (orchestrator != nullptr) {
            std::vector<std::pair<std::string, Json>> module_snapshots;
            module_snapshots.reserve(modules.size());
            for (const std::unique_ptr<IAgentModule>& module : modules) {
                module_snapshots.emplace_back(module->module_id(),
                                              module->export_state_snapshot());
            }
            condenser.set_anchored(orchestrator->scratchpad(), module_snapshots);
        }

        // 8. Handle the Orchestrator's intent (Req 3.3, Req 5). The module records
        // an intent inside execute_action and the loop acts on it here, after the
        // turn is recorded. take_intent() reads and clears.
        if (orchestrator != nullptr) {
            switch (orchestrator->take_intent()) {
            case OrchestratorModule::Intent::completion_requested: {
                // Completion request -> run the deterministic exit gate (Req 5). On
                // success the loop terminates with the gate's completion output; on
                // a must_succeed failure the gate returns a non-success result whose
                // completion_output carries the hook's on_failure_instruction, which
                // we push as next-turn guidance before continuing the loop.
                TerminalResult gate =
                    run_exit_gate(recipe, modules, orchestrator->completion_output());
                if (gate.success) {
                    result.outcome = LoopOutcome::success;
                    result.success = true;
                    result.completion_output = std::move(gate.completion_output);
                    result.run_record = std::move(run_record);
                    return result;
                }
                // Non-success gate: completion_output carries the hook's
                // on_failure_instruction (see run_exit_gate's contract). Inject it
                // as guidance so the next turn can satisfy the gate.
                if (!gate.completion_output.empty()) {
                    condenser.push_guidance(std::move(gate.completion_output));
                }
                break;
            }
            case OrchestratorModule::Intent::condense_requested: {
                // The module only requests a condense after validating the
                // scratchpad (Req 3.3), so the loop trusts it. The anchor was just
                // refreshed above, so the wipe re-renders from the latest
                // scratchpad.
                condenser.condense();
                break;
            }
            case OrchestratorModule::Intent::none:
                break;
            }
        }

        // 9. Post-turn condense pressure (Req 2.6). A wipe clears history, so it may
        // only happen once the scratchpad is valid — otherwise the agent would lose
        // its tail before its required notes were saved (Req 3.3). With no
        // Orchestrator there are no required fields to protect, so treat that as
        // valid. When pressure is high but the scratchpad is invalid, hold the
        // history and nudge the model to checkpoint its notes first.
        if (condenser.should_condense()) {
            const bool scratchpad_ok = orchestrator == nullptr || orchestrator->scratchpad_valid();
            if (scratchpad_ok) {
                if (orchestrator != nullptr) {
                    std::vector<std::pair<std::string, Json>> module_snapshots;
                    module_snapshots.reserve(modules.size());
                    for (const std::unique_ptr<IAgentModule>& module : modules) {
                        module_snapshots.emplace_back(module->module_id(),
                                                      module->export_state_snapshot());
                    }
                    condenser.set_anchored(orchestrator->scratchpad(), module_snapshots);
                }
                condenser.condense();
            } else {
                condenser.push_guidance(
                    "context is nearly full; call OrchestratorModule.checkpoint_notes to save "
                    "the required notes so history can be condensed without losing progress.");
            }
        }
    }

    // Turn-limit terminal (Req 1.5): the loop ran every allowed turn without a
    // passed exit gate. Return the accumulated transcript and RunRecord with a
    // non-success turn_limit outcome.
    result.outcome = LoopOutcome::turn_limit;
    result.success = false;
    result.run_record = std::move(run_record);
    return result;
}

TerminalResult AgentLoop::run_exit_gate(
    const RecipeCartridge& recipe, const std::vector<std::unique_ptr<IAgentModule>>& modules,
    std::string completion_output) {
    // The deterministic recipe exit gate (Req 5). This runs on a complete_recipe
    // request and issues NO backend generate() call — it never touches backend_.

    // No hook: completion completes immediately (Req 5.2).
    if (!recipe.post_llm_validation_hook) {
        TerminalResult result;
        result.outcome = LoopOutcome::success;
        result.success = true;
        result.completion_output = std::move(completion_output);
        return result;
    }

    const ValidationHook& hook = *recipe.post_llm_validation_hook;

    // Run the hook as a deterministic HookCall: find the loaded module by id and
    // call execute_action directly. A HookCall is a recipe-runner call, not an LLM
    // dispatch (Req 5.5), so the expose_actions check that resolve_and_dispatch
    // applies is deliberately NOT applied here — the hook MAY target an action
    // outside expose_actions. Load-time validate_recipe already guaranteed the
    // module is loaded and the action exists, but we defensively treat a missing
    // module as a gate failure. ValidationHook carries no args, so pass an empty
    // object. The module/action is invoked exactly once (Req 5.1 / Property 15).
    IAgentModule* target = nullptr;
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        if (module->module_id() == hook.module) {
            target = module.get();
            break;
        }
    }

    ActionResult hook_result;
    if (target == nullptr) {
        // Should be unreachable after load-time validation; treat as a failure.
        hook_result.success = false;
        hook_result.error_code = "unknown_module";
        hook_result.llm_facing_output = "hook module '" + hook.module + "' is not loaded";
    } else {
        hook_result = target->execute_action(hook.action, Json::object());
    }

    // Hook passed: completion succeeds with the completion output (Req 5.3).
    if (hook_result.success) {
        TerminalResult result;
        result.outcome = LoopOutcome::success;
        result.success = true;
        result.completion_output = std::move(completion_output);
        return result;
    }

    // Hook failed with must_succeed==false: an advisory gate. The spec's exit
    // semantics center on must_succeed; a soft gate does not block completion, so
    // allow it to complete with the completion output.
    if (!hook.must_succeed) {
        TerminalResult result;
        result.outcome = LoopOutcome::success;
        result.success = true;
        result.completion_output = std::move(completion_output);
        return result;
    }

    // Hook failed with must_succeed==true: the loop must NOT exit (Req 5.2).
    // Return a non-success result whose completion_output carries the hook's
    // on_failure_instruction. The run() call site pushes a non-success result's
    // completion_output as next-turn guidance, so this injects the instruction and
    // continues the loop; the loop's own max_turns bound still governs final
    // termination (Req 1.5). outcome is turn_limit so the non-success branch in
    // run() continues rather than terminating.
    TerminalResult result;
    result.outcome = LoopOutcome::turn_limit;
    result.success = false;
    result.completion_output = hook.on_failure_instruction;
    return result;
}

ActionResult AgentLoop::resolve_and_dispatch(
    const std::vector<std::unique_ptr<IAgentModule>>& modules, const RecipeCartridge& recipe,
    const ActionCall& call) {
    // Find the loaded module the decision targets. A module the recipe never
    // loaded (or an id the LLM invented) is unresolvable (Req 1.4).
    IAgentModule* target = nullptr;
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        if (module->module_id() == call.module) {
            target = module.get();
            break;
        }
    }
    if (target == nullptr) {
        ActionResult synthetic;
        synthetic.success = false;
        synthetic.error_code = "unknown_module";
        synthetic.llm_facing_output = "no module named '" + call.module + "' is loaded";
        return synthetic;
    }

    // The LLM may only call actions the recipe exposed for this module. Hooks (a
    // deterministic recipe-driven path, not an LLM dispatch) are task 8.4 and are
    // not consulted here. Resolution is purely by identity and the expose list;
    // llm_facing_output text is never inspected (R19).
    for (const ModuleLoad& load : recipe.load_modules) {
        if (load.module != call.module) {
            continue;
        }
        const bool exposed =
            std::find(load.expose_actions.begin(), load.expose_actions.end(), call.action) !=
            load.expose_actions.end();
        if (!exposed) {
            ActionResult synthetic;
            synthetic.success = false;
            synthetic.error_code = "action_not_exposed";
            synthetic.llm_facing_output =
                "action '" + call.action + "' is not exposed by module '" + call.module + "'";
            return synthetic;
        }
        break;
    }

    // Dispatch exactly one action. execute_action never throws on bad LLM input:
    // unknown actions and invalid args come back as failed ActionResults
    // (unknown_action, invalid_args), which are surfaced as-is (Req 1.4).
    return target->execute_action(call.action, call.args);
}

}  // namespace aquila
