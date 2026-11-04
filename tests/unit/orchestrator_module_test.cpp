#include "aquila/agent/orchestrator_module.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/module.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/scratchpad.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

#include <algorithm>
#include <cstddef>
#include <set>
#include <string>
#include <utility>
#include <vector>

using namespace aquila;

namespace {

// The five scratchpad field names the OrchestratorModule understands. Three are
// scalar strings; two are string arrays. Validation treats a field as satisfied
// when it is present and non-empty, so generated values below are always
// non-empty when a field is supposed to be set.
const std::vector<std::string>& all_fields() {
    static const std::vector<std::string> v{"active_objective", "current_hypothesis",
                                            "verified_facts",
                                            "failed_approaches_do_not_repeat",
                                            "next_immediate_action"};
    return v;
}

bool is_array_field(const std::string& name) {
    return name == "verified_facts" || name == "failed_approaches_do_not_repeat";
}

// A dummy ModuleContext. The OrchestratorModule never touches disk, so any path
// works for the host API and the three actions under test.
ModuleContext make_ctx() {
    ModuleContext ctx;
    ctx.workspace_root = "/tmp/aquila-orchestrator-test";
    return ctx;
}

// Printable-ASCII, non-empty string. The scratchpad is serialized through the
// canonical JSON writer, so values must stay UTF-8 valid; a safe alphabet keeps
// every generated state serializable. Non-empty so a provided field always
// counts as "present and non-empty" for validation.
rc::Gen<std::string> ascii_nonempty() {
    return rc::gen::nonEmpty(rc::gen::container<std::string>(rc::gen::elementOf(
        std::string("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. /"))));
}

// A non-empty array of non-empty ASCII strings, for the array-valued fields.
rc::Gen<std::vector<std::string>> ascii_nonempty_array() {
    return rc::gen::nonEmpty(rc::gen::container<std::vector<std::string>>(ascii_nonempty()));
}

// A random subset of the five field names (used as required_fields and as the
// set of fields to send in a checkpoint). Drawn by independent inclusion coins.
rc::Gen<std::vector<std::string>> gen_field_subset() {
    return rc::gen::map(
        rc::gen::container<std::vector<bool>>(all_fields().size(), rc::gen::arbitrary<bool>()),
        [](const std::vector<bool>& include) {
            std::vector<std::string> out;
            for (std::size_t i = 0; i < all_fields().size(); ++i) {
                if (include[i]) out.push_back(all_fields()[i]);
            }
            return out;
        });
}

// Build a checkpoint_notes args object that sets exactly the given field names,
// each to a freshly generated non-empty value. Returns the args plus the scalar
// and array values chosen so the caller can assert the scratchpad reflects them.
struct CheckpointDraw {
    Json args = Json::object();
    std::vector<std::pair<std::string, std::string>> scalars;
    std::vector<std::pair<std::string, std::vector<std::string>>> arrays;
};

rc::Gen<CheckpointDraw> gen_checkpoint(const std::vector<std::string>& fields) {
    return rc::gen::exec([fields]() {
        CheckpointDraw draw;
        for (const std::string& name : fields) {
            if (is_array_field(name)) {
                const std::vector<std::string> value = *ascii_nonempty_array();
                draw.args[name] = value;
                draw.arrays.emplace_back(name, value);
            } else {
                const std::string value = *ascii_nonempty();
                draw.args[name] = value;
                draw.scalars.emplace_back(name, value);
            }
        }
        return draw;
    });
}

}  // namespace

// ---------------------------------------------------------------------------
// Property 11: Checkpoint validates required fields and merges on success.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 11: checkpoint_notes succeeds exactly when
// every required field ends up present and non-empty; on success the scratchpad
// reflects the provided updates, and on failure error_code == "missing_required_field"
// and the required-field state is unchanged.
// Validates: Requirements 3.2
TEST_CASE("Property 11: checkpoint validates required fields and merges on success",
          "[rapidcheck][orchestrator]") {
    rc::prop("success iff all required fields non-empty; merge on success, no change on fail", [] {
        const std::vector<std::string> required = *gen_field_subset();
        const std::vector<std::string> provided = *gen_field_subset();
        const CheckpointDraw draw = *gen_checkpoint(provided);

        OrchestratorModule module(make_ctx());
        module.configure(Json{{"required_fields", required}});

        // Capture the full state before the call so a failed call can be shown
        // byte-identical afterwards (required-field state unchanged).
        const Json before = module.export_state_snapshot();

        const ActionResult result = module.execute_action("checkpoint_notes", draw.args);

        // The call succeeds exactly when every required field is among the
        // provided (and therefore non-empty) fields.
        const std::set<std::string> provided_set(provided.begin(), provided.end());
        bool all_required_present = true;
        for (const std::string& name : required) {
            if (provided_set.find(name) == provided_set.end()) {
                all_required_present = false;
                break;
            }
        }

        RC_ASSERT(result.success == all_required_present);

        if (all_required_present) {
            // On success the scratchpad reflects exactly the provided updates.
            const AgentScratchpad& pad = module.scratchpad();
            for (const auto& kv : draw.scalars) {
                if (kv.first == "active_objective") {
                    RC_ASSERT(pad.active_objective == kv.second);
                } else if (kv.first == "current_hypothesis") {
                    RC_ASSERT(pad.current_hypothesis == kv.second);
                } else {  // next_immediate_action
                    RC_ASSERT(pad.next_immediate_action == kv.second);
                }
            }
            for (const auto& kv : draw.arrays) {
                if (kv.first == "verified_facts") {
                    RC_ASSERT(pad.verified_facts == kv.second);
                } else {  // failed_approaches_do_not_repeat
                    RC_ASSERT(pad.failed_approaches_do_not_repeat == kv.second);
                }
            }
        } else {
            // On failure the error code is exact and the state is untouched.
            RC_ASSERT(result.error_code == "missing_required_field");
            const Json after = module.export_state_snapshot();
            RC_ASSERT(after == before);
            RC_ASSERT(after.dump() == before.dump());
        }
    });
}

// ---------------------------------------------------------------------------
// Property 12: Condense is requested only after scratchpad validation.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 12: trigger_context_condense yields a
// condense_requested intent exactly when the scratchpad passes required-field
// validation; otherwise it returns a failed ActionResult and produces no intent.
// Validates: Requirements 3.3
TEST_CASE("Property 12: condense is requested only after scratchpad validation",
          "[rapidcheck][orchestrator]") {
    rc::prop("condense_requested iff scratchpad_valid; otherwise fail and no intent", [] {
        const std::vector<std::string> required = *gen_field_subset();
        const std::vector<std::string> provided = *gen_field_subset();
        const CheckpointDraw draw = *gen_checkpoint(provided);

        OrchestratorModule module(make_ctx());
        module.configure(Json{{"required_fields", required}});

        // Optionally seed the scratchpad with a checkpoint; this may or may not
        // satisfy the required fields, so validity varies across cases.
        module.execute_action("checkpoint_notes", draw.args);

        const bool valid = module.scratchpad_valid();
        const ActionResult result =
            module.execute_action("trigger_context_condense", Json::object());

        // Check the result first, then take_intent() exactly once (it clears).
        if (valid) {
            RC_ASSERT(result.success);
            RC_ASSERT(module.take_intent() == OrchestratorModule::Intent::condense_requested);
        } else {
            RC_ASSERT(!result.success);
            RC_ASSERT(module.take_intent() == OrchestratorModule::Intent::none);
        }
    });
}

// ---------------------------------------------------------------------------
// Property 13: Scratchpad snapshot round-trip.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 13: exporting a snapshot, restoring it into a
// fresh OrchestratorModule, and exporting again yields byte-identical JSON.
// Validates: Requirements 3.5
TEST_CASE("Property 13: scratchpad snapshot round-trip", "[rapidcheck][orchestrator]") {
    rc::prop("export -> restore(fresh) -> export is byte-identical", [] {
        // Drive module A to a random state. required_fields is empty so every
        // checkpoint commits, letting us set any subset of fields freely.
        const std::vector<std::string> provided = *gen_field_subset();
        const CheckpointDraw draw = *gen_checkpoint(provided);

        // A random checklist, exercised through configure, so the snapshot's
        // scratchpad.checklist is non-trivial.
        const auto checklist = *rc::gen::container<std::vector<Json>>(
            rc::gen::exec([]() {
                Json item = Json::object();
                item["id"] = *ascii_nonempty();
                item["text"] = *ascii_nonempty();
                item["status"] = *rc::gen::elementOf(std::vector<std::string>{
                    "pending", "done", "skipped"});
                return item;
            }));

        OrchestratorModule a(make_ctx());
        a.configure(Json{{"required_fields", std::vector<std::string>{}},
                         {"checklist", checklist}});
        a.execute_action("checkpoint_notes", draw.args);

        const Json snap_a = a.export_state_snapshot();

        OrchestratorModule b(make_ctx());
        b.restore_state_snapshot(snap_a);
        const Json snap_b = b.export_state_snapshot();

        // Json equality plus a dump() byte comparison (ordered_json preserves key
        // order, so dump() is the byte-identity check).
        RC_ASSERT(snap_a == snap_b);
        RC_ASSERT(snap_a.dump() == snap_b.dump());
    });
}

// ---------------------------------------------------------------------------
// Task 6.7 — Unit test: action set and completion intent.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Requirements 3.1 and 3.4: get_actions() exposes exactly
// {checkpoint_notes, trigger_context_condense, complete_recipe}, each with an
// object-typed parameters schema; complete_recipe sets Intent::completion_requested
// and records the completion output.
TEST_CASE("OrchestratorModule exposes three object-schema actions and signals completion") {
    OrchestratorModule module(make_ctx());

    // Requirement 3.1: exactly the three actions, each with an object schema.
    const std::vector<ActionSchema> actions = module.get_actions();
    std::set<std::string> names;
    for (const ActionSchema& a : actions) {
        names.insert(a.action_name);
        INFO("action " << a.action_name << " must have an object parameters schema");
        REQUIRE(a.parameters_json_schema.is_object());
        REQUIRE(a.parameters_json_schema.contains("type"));
        CHECK(a.parameters_json_schema.at("type").get<std::string>() == "object");
    }
    CHECK(names == std::set<std::string>{"checkpoint_notes", "trigger_context_condense",
                                        "complete_recipe"});

    // No intent before any action runs.
    CHECK(module.take_intent() == OrchestratorModule::Intent::none);

    // Requirement 3.4: complete_recipe succeeds and sets the completion intent.
    // The completion output is private with no getter, so we verify the ok result
    // and the intent rather than reading the stored text.
    const ActionResult result =
        module.execute_action("complete_recipe", Json{{"output", "done text"}});
    CHECK(result.success);
    CHECK(result.error_code.empty());
    CHECK(module.take_intent() == OrchestratorModule::Intent::completion_requested);

    // take_intent clears: a second read returns none.
    CHECK(module.take_intent() == OrchestratorModule::Intent::none);
}
