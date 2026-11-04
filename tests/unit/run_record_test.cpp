#include "aquila/agent/run_record.hpp"
#include "aquila/json.hpp"
#include "aquila/types/scratchpad.hpp"
#include "aquila/types/tool_interaction.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

using namespace aquila;

namespace {

// Top-level object keys of a type's canonical serialization. RunRecord and
// AgentScratchpad both serialize to a JSON object, so iterating items() yields
// exactly the session/memory field names emitted on the wire.
template <class T>
std::set<std::string> top_level_keys(const T& value) {
    Json j;
    to_json(j, value);
    REQUIRE(j.is_object());
    std::set<std::string> keys;
    for (const auto& item : j.items()) {
        keys.insert(item.key());
    }
    return keys;
}

}  // namespace

// Feature: m4-agent-loop, Requirement 6.1: a run starts with a RunRecord holding
// task_id, mode, instance_id, step_index, ground_truth, and the last ToolInteraction.
TEST_CASE("RunRecord populates all D12 session fields") {
    RunRecord r;
    r.task_id = "task-42";
    r.mode = "code";
    r.instance_id = "inst-7";
    r.step_index = 3;
    r.ground_truth = Json::parse(R"({"expected":"HARNESS_OK","path":"harness_smoke.py"})");
    r.last_interaction = ToolInteraction{
        "int-1", "WorkspaceModule", "create_file",
        Json::parse(R"({"path":"harness_smoke.py"})"),
        ActionResult{true, "", "wrote 12 bytes", 12}};

    // Every field is present and carries the value it was given.
    CHECK(r.task_id == "task-42");
    CHECK(r.mode == "code");
    CHECK(r.instance_id == "inst-7");
    CHECK(r.step_index == std::uint64_t{3});
    CHECK(r.ground_truth.at("expected").get<std::string>() == "HARNESS_OK");
    REQUIRE(r.last_interaction.has_value());
    CHECK(r.last_interaction->module == "WorkspaceModule");
    CHECK(r.last_interaction->action == "create_file");
    CHECK(r.last_interaction->result.success);

    // Canonical serialization exposes exactly the D12 session keys, and
    // last_interaction populates through the M1 ToolInteraction serializer.
    const auto text = to_canonical_string(r);
    INFO(text);
    CHECK(text.find("\"task_id\": \"task-42\"") != std::string::npos);
    CHECK(text.find("\"mode\": \"code\"") != std::string::npos);
    CHECK(text.find("\"instance_id\": \"inst-7\"") != std::string::npos);
    CHECK(text.find("\"step_index\": 3") != std::string::npos);
    CHECK(text.find("\"ground_truth\"") != std::string::npos);
    CHECK(text.find("\"last_interaction\"") != std::string::npos);
    // The nested ToolInteraction serializer contributed its own fields.
    CHECK(text.find("\"action\": \"create_file\"") != std::string::npos);

    const auto keys = top_level_keys(r);
    CHECK(keys == std::set<std::string>{"task_id", "mode", "instance_id", "step_index",
                                        "ground_truth", "last_interaction"});
}

// Feature: m4-agent-loop, Requirement 6.3: a C++ run starts fresh with no
// run_state.json import, so loop-owned session metadata (RunRecord) is kept
// disjoint from LLM memory (AgentScratchpad) per D12.
TEST_CASE("RunRecord session fields are disjoint from AgentScratchpad memory fields") {
    // Populate both so no field name is dropped from either serialization.
    RunRecord record;
    record.task_id = "t";
    record.mode = "code";
    record.instance_id = "i";
    record.step_index = 1;
    record.ground_truth = Json::parse(R"({"k":"v"})");
    record.last_interaction = ToolInteraction{
        "id", "ExecutionModule", "run_test_suite", Json::object(),
        ActionResult{true, "", "ok", 0}};

    AgentScratchpad pad;
    pad.active_objective = "obj";
    pad.current_hypothesis = "hyp";
    pad.verified_facts = {"fact"};
    pad.failed_approaches_do_not_repeat = {"nope"};
    pad.next_immediate_action = "act";
    pad.checklist = {{"a", "A", ChecklistStatus::pending}};

    const auto session_keys = top_level_keys(record);
    const auto memory_keys = top_level_keys(pad);

    // Sanity: both carry the full, expected field sets.
    CHECK(session_keys == std::set<std::string>{"task_id", "mode", "instance_id", "step_index",
                                                "ground_truth", "last_interaction"});
    CHECK(memory_keys == std::set<std::string>{"active_objective", "current_hypothesis",
                                               "verified_facts", "failed_approaches_do_not_repeat",
                                               "next_immediate_action", "checklist"});

    // The separation itself: no top-level key of one appears in the other.
    for (const auto& key : session_keys) {
        INFO("session key leaked into memory: " << key);
        CHECK(memory_keys.find(key) == memory_keys.end());
    }
    for (const auto& key : memory_keys) {
        INFO("memory key leaked into session: " << key);
        CHECK(session_keys.find(key) == session_keys.end());
    }
}

// ---------------------------------------------------------------------------
// Task 3.2 — Property 20: Run record round-trip (self-contained section).
// Feature: m4-agent-loop, Property 20: Run record round-trip
// ---------------------------------------------------------------------------

namespace {

// Generate printable-ASCII strings. The canonical serializer rejects invalid
// UTF-8, and Property 20 is about structure preservation, not encoding fuzzing,
// so a safe alphabet keeps every generated record serializable.
rc::Gen<std::string> ascii_string() {
    return rc::gen::container<std::string>(rc::gen::elementOf(
        std::string("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. /")));
}

// A small free-form JSON object with ASCII string keys and values. ground_truth
// is "free-form acceptance context" and ToolInteraction::args is a free-form
// blob, so an object of string fields exercises the Json round-trip without
// reaching for types the serializer treats specially.
rc::Gen<Json> ascii_object() {
    return rc::gen::map(
        rc::gen::container<std::vector<std::pair<std::string, std::string>>>(
            rc::gen::pair(ascii_string(), ascii_string())),
        [](const std::vector<std::pair<std::string, std::string>>& pairs) {
            Json obj = Json::object();
            for (const auto& kv : pairs) {
                obj[kv.first] = kv.second;  // duplicate keys collapse; insertion order kept
            }
            return obj;
        });
}

// ActionResult has a domain invariant (types/action.hpp): error_code is empty
// exactly when success is true. Couple the two so every generated result is
// serializable — Property 20 is about the RunRecord round-trip, not fuzzing
// invalid ActionResults, which the serializer rightly rejects.
rc::Gen<ActionResult> gen_action_result() {
    return rc::gen::mapcat(rc::gen::arbitrary<bool>(), [](bool success) {
        // On failure the code must be snake_case: a leading [a-z] followed by
        // zero or more [a-z0-9_] (is_valid_error_code in types/action.cpp).
        auto fail_code = rc::gen::map(
            rc::gen::pair(rc::gen::elementOf(std::string("abcdefghijklmnopqrstuvwxyz")),
                          rc::gen::container<std::string>(rc::gen::elementOf(
                              std::string("abcdefghijklmnopqrstuvwxyz0123456789_")))),
            [](const std::pair<char, std::string>& parts) {
                return std::string(1, parts.first) + parts.second;
            });
        auto error_code = success ? rc::gen::just(std::string{}) : std::move(fail_code);
        return rc::gen::construct<ActionResult>(rc::gen::just(success), std::move(error_code),
                                                ascii_string(),  // llm_facing_output
                                                rc::gen::arbitrary<std::uint64_t>());
    });
}

rc::Gen<ToolInteraction> gen_tool_interaction() {
    return rc::gen::construct<ToolInteraction>(ascii_string(),  // id
                                               ascii_string(),  // module
                                               ascii_string(),  // action
                                               ascii_object(),  // args
                                               gen_action_result());
}

// last_interaction is a std::optional, so roughly half the records carry an
// interaction and half omit the key (the empty-record path).
rc::Gen<std::optional<ToolInteraction>> gen_maybe_interaction() {
    return rc::gen::mapcat(rc::gen::arbitrary<bool>(), [](bool present) {
        return present
                   ? rc::gen::map(gen_tool_interaction(),
                                  [](ToolInteraction ti) {
                                      return std::optional<ToolInteraction>(std::move(ti));
                                  })
                   : rc::gen::just(std::optional<ToolInteraction>{});
    });
}

rc::Gen<RunRecord> gen_run_record() {
    return rc::gen::construct<RunRecord>(ascii_string(),  // task_id
                                         ascii_string(),  // mode
                                         ascii_string(),  // instance_id
                                         rc::gen::arbitrary<std::uint64_t>(),  // step_index
                                         ascii_object(),         // ground_truth
                                         gen_maybe_interaction());  // last_interaction
}

}  // namespace

// Property 20: Run record round-trip.
// parse<RunRecord>(to_canonical_string(r)) == r, and re-serialization is
// byte-identical. Validates: Requirements 6.4
TEST_CASE("Property 20: run record round-trip", "[rapidcheck][run_record]") {
    rc::prop("parse(to_canonical_string(r)) == r and re-serialization is byte-identical", [] {
        // Draw from the explicit generator (no Arbitrary<RunRecord> is
        // registered) so RapidCheck still shrinks on the component values.
        const RunRecord record = *gen_run_record();
        const std::string text = to_canonical_string(record);
        const RunRecord parsed = parse<RunRecord>(text);
        RC_ASSERT(parsed == record);
        RC_ASSERT(to_canonical_string(parsed) == text);
    });
}
