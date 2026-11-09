// aquila/agent/agent_loop.hpp
#pragma once

#include "aquila/agent/context_condenser.hpp"
#include "aquila/agent/orchestrator_module.hpp"
#include "aquila/agent/run_record.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/recipe.hpp"
#include "aquila/types/tool_interaction.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace aquila {

namespace logging {
class RunLogger;
}

// Why the loop stopped (Req 1.5, 5.3, 7.4).
enum class LoopOutcome { success, turn_limit, aborted };

// One recorded turn; the transcript is the ordered list of these (Req 1.6).
struct TurnRecord {
    std::uint64_t index = 0;
    std::string raw_reply;                 // backend content for this turn
    bool parsed = false;                   // false on a parse failure (Req 1.3)
    std::optional<ActionCall> call;        // the parsed decision, when parsed
    std::optional<ToolInteraction> interaction;  // the dispatched tool cycle, if any
    std::string note;                      // corrective/guidance text, if any

    bool operator==(const TurnRecord&) const = default;
};

// Terminal result of a run (Req 1.5, 5.3, 7.4).
struct TerminalResult {
    LoopOutcome outcome = LoopOutcome::turn_limit;
    bool success = false;                  // true only on a passed exit gate
    std::string completion_output;         // from complete_recipe when success
    std::vector<TurnRecord> transcript;    // byte-identical across identical runs
    RunRecord run_record;
};

// Per-run configuration. CPU-first: the tier defaults to a CPU tier (Req 4.2).
struct LoopConfig {
    RuntimeTierConfig tier = RuntimeTierConfig::default_config();
    std::string system_prompt;
    std::string task_id;
    std::string mode;
    std::string instance_id;
    Json ground_truth = Json::object();
    CondenserStrategy context_strategy = CondenserStrategy::sac;
    std::uint32_t max_repeated_calls = 0;

    // M8 Streaming, Progress & Cancellation Callbacks:
    TokenCallback on_token = {};
    std::function<void(const TurnRecord&)> on_turn = {};
    std::function<bool()> check_cancelled = {};

    // Logging:
    std::shared_ptr<logging::RunLogger> logger = nullptr;
    bool enable_disk_logging = true;
};

// Single-threaded, deterministic driver (Req 1, Req 5, R14). No async, no
// coroutines: every turn's state is owned by this frame or the condenser. Given
// the same recipe, request, and (replayed) backend, two runs produce
// byte-identical transcripts (Req 1.6).
class AgentLoop {
public:
    AgentLoop(IInferenceBackend& backend, const ModuleRegistry& registry, ModuleContext module_ctx);

    // Loads + validates the recipe (SchemaError at load time, Req 5.4), builds the
    // module set, seeds the condenser's pinned prefix, creates the per-run
    // RunRecord, then runs turns until terminal or the turn limit.
    TerminalResult run(const RecipeCartridge& recipe, const std::string& user_request,
                       const LoopConfig& config);

    // The {thought, module, action, args} JSON Schema the backend enforces,
    // matching M1 ActionCall (required, additionalProperties:false).
    [[nodiscard]] static Json action_call_schema(const RecipeCartridge* recipe = nullptr);

private:
    // Deterministic generation parameters: a fixed low temperature plus a
    // max_thought_tokens-derived output budget, constrained to the action-call
    // JSON schema (R14).
    [[nodiscard]] GenerationParams generation_params(const TierLimits& limits, const RecipeCartridge* recipe = nullptr) const;

    // Runs the recipe's deterministic exit gate (Req 5) when complete_recipe is
    // requested. With no post_llm_validation_hook, completion succeeds immediately
    // (Req 5.2); otherwise the hook runs as a deterministic HookCall — a direct
    // execute_action on the loaded module, NOT an LLM dispatch, so expose_actions
    // is not consulted (Req 5.5) and NO backend generation happens (Req 5.1). The
    // hook module/action is invoked exactly once through `modules`.
    //
    // Contract with the turn cycle (Req 5.3): on a passed/absent gate this returns
    // a success TerminalResult carrying `completion_output`; on a must_succeed
    // failure it returns a NON-success TerminalResult whose `completion_output`
    // field carries the hook's `on_failure_instruction`. The run() call site
    // pushes a non-success result's completion_output as next-turn guidance, which
    // injects the on_failure_instruction and continues the loop.
    //
    // Static (like resolve_and_dispatch): it needs no `this` state and must never
    // touch backend_.
    [[nodiscard]] static TerminalResult run_exit_gate(
        const RecipeCartridge& recipe, const std::vector<std::unique_ptr<IAgentModule>>& modules,
        std::string completion_output, std::shared_ptr<logging::RunLogger> logger = nullptr);

    // Resolves a parsed decision to an ActionResult (Req 1.4): finds the loaded
    // module and checks the recipe's expose_actions, returning a synthetic failed
    // result (`unknown_module`, `action_not_exposed`) when resolution fails, or
    // dispatching exactly one execute_action otherwise. All branching is on the
    // module identity and expose list, never on llm_facing_output text (R19).
    [[nodiscard]] static ActionResult resolve_and_dispatch(
        const std::vector<std::unique_ptr<IAgentModule>>& modules, const RecipeCartridge& recipe,
        const ActionCall& call);

    IInferenceBackend& backend_;
    const ModuleRegistry& registry_;
    ModuleContext module_ctx_;
};

}  // namespace aquila
