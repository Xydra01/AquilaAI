// aquila/agent/orchestrator_module.hpp
#pragma once
#include "aquila/modules/module.hpp"
#include "aquila/types/recipe.hpp"
#include "aquila/types/scratchpad.hpp"
#include "aquila/types/task_ledger.hpp"
#include <map>
#include <string>
#include <vector>

namespace aquila {

// Meta-module: owns the AgentScratchpad and TaskLedger, exposing progress,
// ledger tracking, and completion as first-class actions (R11).
// Registered as built-in id "OrchestratorModule".
class OrchestratorModule final : public ModuleBase {
public:
    explicit OrchestratorModule(const ModuleContext& ctx);

    [[nodiscard]] std::string module_id() const override { return "OrchestratorModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;  // checkpoint_notes, update_task_ledger, trigger_context_condense, complete_recipe

    // initial_state: {required_fields?: [..], checklist?: [..], task_ledger?: {..}}.
    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;   // scratchpad + task_ledger + checklist, round-trips byte-equal
    [[nodiscard]] Json export_context_summary() const override;  // omits duplicate scratchpad/ledger rendered top-level by condenser
    void restore_state_snapshot(const Json& snapshot) override;

    // Host API (not exposed to the LLM): the loop reads the scratchpad and ledger
    // for the anchored block and consults validation/completion intents.
    [[nodiscard]] const AgentScratchpad& scratchpad() const noexcept { return pad_; }
    [[nodiscard]] bool scratchpad_valid() const;     // required_fields present & non-empty
    [[nodiscard]] std::vector<std::string> missing_fields() const;

    [[nodiscard]] const TaskLedger& ledger() const noexcept { return ledger_; }
    [[nodiscard]] TaskLedger& mutable_ledger() noexcept { return ledger_; }
    void set_task_ledger(TaskLedger ledger);
    void sync_ledger_to_disk() const;

    // The text recorded by the most recent complete_recipe (Req 3.4).
    [[nodiscard]] const std::string& completion_output() const noexcept { return completion_output_; }
    [[nodiscard]] const std::map<std::string, RecipeCartridge>& registered_recipes() const noexcept {
        return registered_recipes_;
    }

    // Set by complete_recipe / trigger_context_condense so the loop can act on the
    // intent after execute_action returns (ModuleBase stays side-effect-local).
    enum class Intent { none, condense_requested, completion_requested };
    [[nodiscard]] Intent take_intent();              // reads and clears

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    ActionResult checkpoint_notes(const Json& args);          // updates pad_ fields and optional ledger checkoffs
    ActionResult update_task_ledger(const Json& args);        // updates ledger_ milestones, focus, and status
    ActionResult trigger_context_condense(const Json& args);  // validates then requests wipe (Req 3.3)
    ActionResult complete_recipe(const Json& args);           // verifies ledger completion and requests completion gate (Req 3.4)
    ActionResult register_new_recipe(const Json& args);       // dynamic recipe registration (M7)

    [[nodiscard]] static bool field_nonempty(const AgentScratchpad& pad,
                                             const std::string& name) noexcept;

    ModuleContext ctx_;
    AgentScratchpad pad_;
    TaskLedger ledger_;
    std::vector<std::string> required_fields_;
    std::map<std::string, RecipeCartridge> registered_recipes_;
    Intent intent_ = Intent::none;
    std::string completion_output_;
};

}  // namespace aquila
