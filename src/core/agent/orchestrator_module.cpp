#include "aquila/agent/orchestrator_module.hpp"

#include <filesystem>
#include <fstream>

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
         "Save progress into the scratchpad and optionally update ledger milestones. Required fields must be non-empty before a context wipe.",
         schema(R"({"type":"object","properties":{"active_objective":{"type":"string"},"current_hypothesis":{"type":"string"},"verified_facts":{"type":"array","items":{"type":"string"}},"failed_approaches_do_not_repeat":{"type":"array","items":{"type":"string"}},"next_immediate_action":{"type":"string"},"checklist":{"type":"array"},"notes":{"type":"object"},"current_status":{"type":"string"},"completed_steps":{"type":"array","items":{"type":"string"}},"in_progress_step":{"type":"string"}},"additionalProperties":true})")},
        {"update_task_ledger",
         "Update procedural progress in the active Task Ledger. Mark steps completed, set current focus, or add notes.",
         schema(R"({"type":"object","properties":{"current_status":{"type":"string"},"completed_steps":{"type":"array","items":{"type":"string"}},"in_progress_step":{"type":"string"},"blocked_steps":{"type":"array","items":{"type":"string"}},"skipped_steps":{"type":"array","items":{"type":"string"}},"notes":{"type":"string"},"new_steps":{"type":"array","items":{"type":"string"}}},"additionalProperties":true})")},
        {"trigger_context_condense",
         "Request a context condense (wipe) once the scratchpad is saved and valid.",
         schema(R"({"type":"object","properties":{},"additionalProperties":false})")},
        {"complete_recipe",
         "Declare the recipe finished; the loop runs the deterministic exit gate.",
         schema(R"({"type":"object","properties":{"output":{"type":"string"}},"additionalProperties":false})")},
        {"register_new_recipe",
         "Dynamically register a new workflow recipe cartridge.",
         schema(R"({"type":"object","properties":{"recipe":{"type":"object"}},"required":["recipe"],"additionalProperties":false})")},
    };
}

void OrchestratorModule::configure(const Json& initial_state) {
    expect_object(initial_state, "");
    reject_unknown(initial_state, "", {"required_fields", "checklist", "task_ledger"});
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
        if (ledger_.steps.empty()) {
            for (const auto& item : pad_.checklist) {
                ledger_.steps.push_back(LedgerStep{item.id, item.text, LedgerStepStatus::pending, {}});
            }
        }
    }
    if (initial_state.contains("task_ledger")) {
        from_json(initial_state["task_ledger"], ledger_, "/task_ledger");
    }
    sync_ledger_to_disk();
}

Json OrchestratorModule::export_state_snapshot() const {
    Json s = Json::object();
    s["required_fields"] = required_fields_;
    Json pad;
    to_json(pad, pad_);
    s["scratchpad"] = std::move(pad);
    Json led;
    to_json(led, ledger_);
    s["task_ledger"] = std::move(led);
    s["registered_recipes"] = Json::array();
    for (const auto& [id, c] : registered_recipes_) {
        (void)id;
        Json r;
        to_json(r, c);
        s["registered_recipes"].push_back(std::move(r));
    }
    return s;
}

Json OrchestratorModule::export_context_summary() const {
    // ContextCondenser already renders scratchpad and task_ledger top-level in the anchored block,
    // so omit duplicate payloads here and list recipe IDs only.
    Json s = Json::object();
    s["required_fields"] = required_fields_;
    s["registered_recipe_ids"] = Json::array();
    for (const auto& [id, c] : registered_recipes_) {
        (void)c;
        s["registered_recipe_ids"].push_back(id);
    }
    return s;
}

void OrchestratorModule::restore_state_snapshot(const Json& snapshot) {
    expect_object(snapshot, "");
    reject_unknown(snapshot, "", {"required_fields", "scratchpad", "registered_recipes", "task_ledger"});
    required_fields_ =
        read_string_array(require(snapshot, "", "required_fields"), "/required_fields");
    from_json(require(snapshot, "", "scratchpad"), pad_, "/scratchpad");
    if (snapshot.contains("task_ledger")) {
        from_json(snapshot["task_ledger"], ledger_, "/task_ledger");
    }
    registered_recipes_.clear();
    if (snapshot.contains("registered_recipes")) {
        for (const auto& r_json : snapshot["registered_recipes"]) {
            RecipeCartridge c;
            from_json(r_json, c, "/registered_recipes");
            registered_recipes_[c.recipe_id] = std::move(c);
        }
    }
    sync_ledger_to_disk();
}

void OrchestratorModule::set_task_ledger(TaskLedger ledger) {
    ledger_ = std::move(ledger);
    sync_ledger_to_disk();
}

void OrchestratorModule::sync_ledger_to_disk() const {
    if (ctx_.workspace_root.empty() || (ledger_.steps.empty() && ledger_.objective.empty())) {
        return;
    }
    try {
        const auto tasks_dir = ctx_.workspace_root / "Agent-Tasks";
        std::error_code ec;
        std::filesystem::create_directories(tasks_dir, ec);
        std::string fname = ledger_.task_id.empty() ? "task_ledger.md" : (ledger_.task_id + "_ledger.md");
        const auto out_path = tasks_dir / fname;
        std::ofstream ofs(out_path, std::ios::binary | std::ios::trunc);
        if (ofs) {
            ofs << ledger_.render_markdown();
        }
    } catch (...) {
        // Best-effort disk persistence
    }
}

// --- Action bodies + intent coordination (Req 3.2-3.4) ---------------------

ActionResult OrchestratorModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "checkpoint_notes") return checkpoint_notes(args);
    if (action_name == "update_task_ledger") return update_task_ledger(args);
    if (action_name == "trigger_context_condense") return trigger_context_condense(args);
    if (action_name == "complete_recipe") return complete_recipe(args);
    if (action_name == "register_new_recipe") return register_new_recipe(args);
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

ActionResult OrchestratorModule::checkpoint_notes(const Json& raw_args) {
    AgentScratchpad merged = pad_;
    auto extract_fields = [&](const Json& src) {
        if (!src.is_object()) return;
        if (src.contains("active_objective") && src["active_objective"].is_string()) {
            merged.active_objective = src["active_objective"].get<std::string>();
        }
        if (src.contains("current_hypothesis") && src["current_hypothesis"].is_string()) {
            merged.current_hypothesis = src["current_hypothesis"].get<std::string>();
        }
        if (src.contains("verified_facts") && src["verified_facts"].is_array()) {
            merged.verified_facts = read_string_array(src["verified_facts"], "/verified_facts");
        }
        if (src.contains("failed_approaches_do_not_repeat") && src["failed_approaches_do_not_repeat"].is_array()) {
            merged.failed_approaches_do_not_repeat = read_string_array(
                src["failed_approaches_do_not_repeat"], "/failed_approaches_do_not_repeat");
        }
        if (src.contains("next_immediate_action") && src["next_immediate_action"].is_string()) {
            merged.next_immediate_action = src["next_immediate_action"].get<std::string>();
        }
    };
    if (raw_args.contains("notes") && raw_args["notes"].is_object()) {
        extract_fields(raw_args["notes"]);
    }
    extract_fields(raw_args);

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

    // Optional atomic co-update of task ledger
    bool ledger_modified = false;
    if (raw_args.contains("current_status") && raw_args["current_status"].is_string()) {
        ledger_.current_status = raw_args["current_status"].get<std::string>();
        ledger_modified = true;
    }
    auto apply_ledger_items = [&](const std::string& key, LedgerStepStatus st) {
        if (!raw_args.contains(key)) return;
        const auto& val = raw_args[key];
        auto process = [&](const Json& item) {
            std::string q;
            if (item.is_string()) q = item.get<std::string>();
            else if (item.is_number_integer()) q = std::to_string(item.get<int64_t>());
            if (!q.empty() && ledger_.mark_step(q, st)) ledger_modified = true;
        };
        if (val.is_array()) {
            for (const auto& item : val) process(item);
        } else {
            process(val);
        }
    };
    apply_ledger_items("completed_steps", LedgerStepStatus::completed);
    apply_ledger_items("in_progress_step", LedgerStepStatus::in_progress);

    if (ledger_modified) {
        sync_ledger_to_disk();
    }

    return ok("scratchpad checkpoint saved");
}

ActionResult OrchestratorModule::update_task_ledger(const Json& args) {
    if (!args.is_object()) {
        return fail("invalid_arguments", "Arguments must be a JSON object");
    }

    bool modified = false;
    if (args.contains("objective") && args["objective"].is_string()) {
        ledger_.objective = args["objective"].get<std::string>();
        modified = true;
    }
    if (args.contains("current_status") && args["current_status"].is_string()) {
        ledger_.current_status = args["current_status"].get<std::string>();
        modified = true;
    }

    std::string general_notes;
    if (args.contains("notes") && args["notes"].is_string()) {
        general_notes = args["notes"].get<std::string>();
    }

    auto apply_steps = [&](const std::string& key, LedgerStepStatus st) {
        if (!args.contains(key)) return;
        const auto& val = args[key];
        auto process = [&](const Json& item) {
            std::string q;
            if (item.is_string()) q = item.get<std::string>();
            else if (item.is_number_integer()) q = std::to_string(item.get<int64_t>());
            if (!q.empty() && ledger_.mark_step(q, st, general_notes)) {
                modified = true;
            }
        };
        if (val.is_array()) {
            for (const auto& item : val) process(item);
        } else {
            process(val);
        }
    };

    apply_steps("completed_steps", LedgerStepStatus::completed);
    apply_steps("in_progress_step", LedgerStepStatus::in_progress);
    apply_steps("in_progress_steps", LedgerStepStatus::in_progress);
    apply_steps("blocked_steps", LedgerStepStatus::blocked);
    apply_steps("skipped_steps", LedgerStepStatus::skipped);
    apply_steps("mark_completed", LedgerStepStatus::completed);

    if (args.contains("step_id")) {
        std::string q;
        if (args["step_id"].is_string()) q = args["step_id"].get<std::string>();
        else if (args["step_id"].is_number_integer()) q = std::to_string(args["step_id"].get<int64_t>());
        LedgerStepStatus st = LedgerStepStatus::completed;
        if (args.contains("status") && args["status"].is_string()) {
            st = parse_ledger_status(args["status"].get<std::string>());
        }
        if (!q.empty() && ledger_.mark_step(q, st, general_notes)) {
            modified = true;
        }
    }

    if (args.contains("new_steps") && args["new_steps"].is_array()) {
        for (const auto& item : args["new_steps"]) {
            if (item.is_string()) {
                ledger_.add_step(item.get<std::string>());
                modified = true;
            } else if (item.is_object() && item.contains("description") && item["description"].is_string()) {
                std::string id = item.value("id", "");
                std::string desc = item["description"].get<std::string>();
                ledger_.add_step(desc, id);
                modified = true;
            }
        }
    }

    if (modified) {
        sync_ledger_to_disk();
    }

    const auto incomplete = ledger_.incomplete_steps();
    std::string msg = "Task ledger updated (" +
                      std::to_string(ledger_.steps.size() - incomplete.size()) +
                      "/" + std::to_string(ledger_.steps.size()) + " steps completed).";
    if (incomplete.empty()) {
        msg += " All mandatory steps completed!";
    } else {
        msg += " Remaining incomplete steps: " + std::to_string(incomplete.size()) + ".";
    }
    return ok(msg);
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
    // Auto-satisfy trailing meta-steps whose sole purpose is calling complete_recipe
    // (avoiding a circular trap where calling complete_recipe is rejected because the
    // "Call OrchestratorModule complete_recipe to finish" step is still pending).
    auto is_completion_meta_step = [](const std::string& desc) {
        std::string lower = desc;
        for (char& ch : lower) {
            ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
        }
        return lower.find("complete_recipe") != std::string::npos ||
               lower == "complete recipe" ||
               lower.find("complete the recipe") != std::string::npos;
    };
    bool meta_auto_marked = false;
    for (auto& step : ledger_.steps) {
        if ((step.status == LedgerStepStatus::pending || step.status == LedgerStepStatus::in_progress) &&
            is_completion_meta_step(step.description)) {
            step.status = LedgerStepStatus::completed;
            meta_auto_marked = true;
        }
    }
    if (meta_auto_marked) {
        sync_ledger_to_disk();
    }

    if (!ledger_.all_mandatory_completed()) {
        const auto incomplete = ledger_.incomplete_steps();
        std::string msg = "Cannot complete recipe: mandatory task ledger step(s) still incomplete:\n";
        for (std::size_t i = 0; i < incomplete.size(); ++i) {
            msg += "  - " + incomplete[i] + "\n";
        }
        msg += "Mark them completed or skipped via update_task_ledger first.";
        return fail("incomplete_ledger_steps", msg);
    }
    // Req 3.4: record the optional completion output and signal the loop to run
    // the deterministic exit gate; the module itself never runs the hook.
    completion_output_ = args.value("output", std::string{});
    intent_ = Intent::completion_requested;
    return ok("recipe completion requested");
}

ActionResult OrchestratorModule::register_new_recipe(const Json& args) {
    RecipeCartridge cartridge;
    try {
        from_json(args["recipe"], cartridge, "/recipe");
    } catch (const SchemaError& e) {
        return fail("invalid_cartridge", "recipe validation failed: " + std::string(e.what()));
    }

    try {
        const auto recipes_dir = ctx_.workspace_root / ".aquila" / "recipes";
        std::error_code ec;
        std::filesystem::create_directories(recipes_dir, ec);
        const auto recipe_path = recipes_dir / (cartridge.recipe_id + ".recipe.json");
        std::ofstream ofs(recipe_path, std::ios::binary | std::ios::trunc);
        if (ofs) {
            ofs << to_canonical_string(cartridge);
        }
    } catch (...) {
        // Disk write is best-effort for persistence; memory registration still succeeds.
    }

    registered_recipes_[cartridge.recipe_id] = cartridge;
    return ok("recipe '" + cartridge.recipe_id + "' registered successfully");
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
