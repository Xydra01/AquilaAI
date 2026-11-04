// aquila/agent/orchestrator_module.hpp
#pragma once
#include "aquila/modules/module.hpp"
#include "aquila/types/scratchpad.hpp"
#include <string>
#include <vector>

namespace aquila {

// Meta-module: owns the AgentScratchpad and exposes progress + completion as
// first-class actions (R11). Registered as built-in id "OrchestratorModule".
class OrchestratorModule final : public ModuleBase {
public:
    explicit OrchestratorModule(const ModuleContext& ctx);

    [[nodiscard]] std::string module_id() const override { return "OrchestratorModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;  // checkpoint_notes, trigger_context_condense, complete_recipe (Req 3.1)

    // initial_state: {required_fields?: [..] , checklist?: [..]}. required_fields are
    // the recipe's scratchpad_checklist names that must be non-empty before a wipe.
    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;   // scratchpad + checklist, round-trips byte-equal (Req 3.5)
    void restore_state_snapshot(const Json& snapshot) override;

    // Host API (not exposed to the LLM): the loop reads the scratchpad for the
    // anchored block and consults validation/completion intents.
    [[nodiscard]] const AgentScratchpad& scratchpad() const noexcept { return pad_; }
    [[nodiscard]] bool scratchpad_valid() const;     // required_fields present & non-empty
    [[nodiscard]] std::vector<std::string> missing_fields() const;

    // The text recorded by the most recent complete_recipe (Req 3.4). The loop
    // reads it when handling Intent::completion_requested to feed the exit gate;
    // empty until the LLM calls complete_recipe.
    [[nodiscard]] const std::string& completion_output() const noexcept { return completion_output_; }

    // Set by complete_recipe / trigger_context_condense so the loop can act on the
    // intent after execute_action returns (ModuleBase stays side-effect-local).
    enum class Intent { none, condense_requested, completion_requested };
    [[nodiscard]] Intent take_intent();              // reads and clears

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    ActionResult checkpoint_notes(const Json& args);          // updates pad_ fields (Req 3.2)
    ActionResult trigger_context_condense(const Json& args);  // validates then requests wipe (Req 3.3)
    ActionResult complete_recipe(const Json& args);           // requests completion gate (Req 3.4)

    // True iff the named scratchpad field exists and is non-empty in `pad`.
    // Unknown names are treated as empty so a stray required_field can never
    // silently pass validation. Shared by checkpoint_notes, scratchpad_valid,
    // and missing_fields.
    [[nodiscard]] static bool field_nonempty(const AgentScratchpad& pad,
                                             const std::string& name) noexcept;

    ModuleContext ctx_;
    AgentScratchpad pad_;
    std::vector<std::string> required_fields_;
    Intent intent_ = Intent::none;
    std::string completion_output_;
};

}  // namespace aquila
