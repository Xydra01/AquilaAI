#include "aquila/agent/orchestrator_module.hpp"

namespace aquila {

using namespace json_io;

namespace {

Json schema(const char* text) {
    return Json::parse(text);
}

}  // namespace

OrchestratorModule::OrchestratorModule(const ModuleContext& ctx) : ctx_(ctx) {}

std::vector<ActionSchema> OrchestratorModule::get_actions() const {
    return {
        {"checkpoint_notes",
         "Save progress into the scratchpad. Required fields must be non-empty before a context wipe.",
         schema(R"({"type":"object","properties":{"active_objective":{"type":"string"},"current_hypothesis":{"type":"string"},"verified_facts":{"type":"array","items":{"type":"string"}},"failed_approaches_do_not_repeat":{"type":"array","items":{"type":"string"}},"next_immediate_action":{"type":"string"}},"additionalProperties":false})")},
        {"trigger_context_condense",
         "Request a context condense (wipe) once the scratchpad is saved and valid.",
         schema(R"({"type":"object","properties":{},"additionalProperties":false})")},
        {"complete_recipe",
         "Declare the recipe finished; the loop runs the deterministic exit gate.",
         schema(R"({"type":"object","properties":{"output":{"type":"string"}},"additionalProperties":false})")},
    };
}

void OrchestratorModule::configure(const Json& initial_state) {
    expect_object(initial_state, "");
    reject_unknown(initial_state, "", {"required_fields", "checklist"});
    if (initial_state.contains("required_fields")) {
        required_fields_ =
            read_string_array(initial_state["required_fields"], "/required_fields");
    }
    if (initial_state.contains("checklist")) {
        pad_.checklist = read_array<ChecklistItem>(
            initial_state["checklist"], "/checklist",
            [](const Json& e, const std::string& p) {
                ChecklistItem item;
                from_json(e, item, p);
                return item;
            });
    }
}

Json OrchestratorModule::export_state_snapshot() const {
    Json s = Json::object();
    s["required_fields"] = required_fields_;
    Json pad;
    to_json(pad, pad_);
    s["scratchpad"] = std::move(pad);
    return s;
}

void OrchestratorModule::restore_state_snapshot(const Json& snapshot) {
    expect_object(snapshot, "");
    reject_unknown(snapshot, "", {"required_fields", "scratchpad"});
    required_fields_ =
        read_string_array(require(snapshot, "", "required_fields"), "/required_fields");
    from_json(require(snapshot, "", "scratchpad"), pad_, "/scratchpad");
}

// --- Action bodies + intent coordination (Req 3.2-3.4) ---------------------

ActionResult OrchestratorModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "checkpoint_notes") return checkpoint_notes(args);
    if (action_name == "trigger_context_condense") return trigger_context_condense(args);
    if (action_name == "complete_recipe") return complete_recipe(args);
    return fail("unknown_action", "OrchestratorModule has no action '" + action_name + "'");
}

bool OrchestratorModule::field_nonempty(const AgentScratchpad& pad,
                                        const std::string& name) noexcept {
    if (name == "active_objective") return !pad.active_objective.empty();
    if (name == "current_hypothesis") return !pad.current_hypothesis.empty();
    if (name == "verified_facts") return !pad.verified_facts.empty();
    if (name == "failed_approaches_do_not_repeat") {
        return !pad.failed_approaches_do_not_repeat.empty();
    }
    if (name == "next_immediate_action") return !pad.next_immediate_action.empty();
    return false;  // unknown field names never satisfy a required-field check
}

ActionResult OrchestratorModule::checkpoint_notes(const Json& args) {
    // Req 3.2 / Property 11: merge the supplied subset of scratchpad fields, then
    // require every recipe-required field to be non-empty. On failure the stored
    // scratchpad must be unchanged, so we merge into a copy and only commit when
    // validation passes. args keys were already restricted to this schema's
    // properties by ModuleBase, so each present key is one of the five below.
    AgentScratchpad merged = pad_;
    if (args.contains("active_objective")) {
        merged.active_objective = read_string(args["active_objective"], "/active_objective");
    }
    if (args.contains("current_hypothesis")) {
        merged.current_hypothesis =
            read_string(args["current_hypothesis"], "/current_hypothesis");
    }
    if (args.contains("verified_facts")) {
        merged.verified_facts = read_string_array(args["verified_facts"], "/verified_facts");
    }
    if (args.contains("failed_approaches_do_not_repeat")) {
        merged.failed_approaches_do_not_repeat = read_string_array(
            args["failed_approaches_do_not_repeat"], "/failed_approaches_do_not_repeat");
    }
    if (args.contains("next_immediate_action")) {
        merged.next_immediate_action =
            read_string(args["next_immediate_action"], "/next_immediate_action");
    }

    std::vector<std::string> missing;
    for (const std::string& name : required_fields_) {
        if (!field_nonempty(merged, name)) missing.push_back(name);
    }
    if (!missing.empty()) {
        std::string joined;
        for (std::size_t i = 0; i < missing.size(); ++i) {
            if (i != 0) joined += ", ";
            joined += missing[i];
        }
        // pad_ is untouched: the merge lived only in `merged`.
        return fail("missing_required_field",
                    "required scratchpad field(s) empty: " + joined);
    }

    pad_ = std::move(merged);  // commit only after validation succeeds
    return ok("scratchpad checkpoint saved");
}

ActionResult OrchestratorModule::trigger_context_condense(const Json& /*args*/) {
    // Req 3.3 / Property 12: only request a wipe once the scratchpad is saved and
    // valid, so the loop never discards context before notes are durable. On
    // failure leave intent_ untouched (no intent produced).
    if (!scratchpad_valid()) {
        const std::vector<std::string> missing = missing_fields();
        std::string joined;
        for (std::size_t i = 0; i < missing.size(); ++i) {
            if (i != 0) joined += ", ";
            joined += missing[i];
        }
        return fail("scratchpad_incomplete",
                    "cannot condense: save required scratchpad field(s) first: " + joined);
    }
    intent_ = Intent::condense_requested;
    return ok("context condense requested");
}

ActionResult OrchestratorModule::complete_recipe(const Json& args) {
    // Req 3.4: record the optional completion output and signal the loop to run
    // the deterministic exit gate; the module itself never runs the hook.
    completion_output_ = args.value("output", std::string{});
    intent_ = Intent::completion_requested;
    return ok("recipe completion requested");
}

bool OrchestratorModule::scratchpad_valid() const {
    for (const std::string& name : required_fields_) {
        if (!field_nonempty(pad_, name)) return false;
    }
    return true;
}

std::vector<std::string> OrchestratorModule::missing_fields() const {
    std::vector<std::string> out;
    for (const std::string& name : required_fields_) {
        if (!field_nonempty(pad_, name)) out.push_back(name);
    }
    return out;
}

OrchestratorModule::Intent OrchestratorModule::take_intent() {
    const Intent current = intent_;
    intent_ = Intent::none;
    return current;
}

}  // namespace aquila
