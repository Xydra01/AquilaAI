#include "aquila/agent/context_condenser.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/module.hpp"
#include "aquila/types/message.hpp"
#include "aquila/types/scratchpad.hpp"
#include "aquila/types/tool_interaction.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

using namespace aquila;

namespace {

// Printable-ASCII strings. The anchored block is rendered through the canonical
// JSON serializer and Message content must stay UTF-8 valid; a safe alphabet
// keeps every generated condenser state serializable without reaching for
// encoding fuzzing (these properties test structure, not UTF-8 handling).
rc::Gen<std::string> ascii_string() {
    return rc::gen::container<std::string>(rc::gen::elementOf(
        std::string("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. /")));
}

// A non-empty ASCII string of a chosen byte length, built from a fixed alphabet.
// Used to generate tool outputs with a controlled size relative to the tier's
// tool_output_chars budget so the under/over-budget branches are both exercised.
rc::Gen<std::string> ascii_string_of_length(std::size_t len) {
    return rc::gen::map(rc::gen::container<std::vector<char>>(
                            len, rc::gen::elementOf(std::string(
                                     "abcdefghijklmnopqrstuvwxyz0123456789"))),
                        [](const std::vector<char>& chars) {
                            return std::string(chars.begin(), chars.end());
                        });
}

// A small free-form JSON object with ASCII keys/values for ToolInteraction::args.
rc::Gen<Json> ascii_object() {
    return rc::gen::map(
        rc::gen::container<std::vector<std::pair<std::string, std::string>>>(
            rc::gen::pair(ascii_string(), ascii_string())),
        [](const std::vector<std::pair<std::string, std::string>>& pairs) {
            Json obj = Json::object();
            for (const auto& kv : pairs) {
                obj[kv.first] = kv.second;
            }
            return obj;
        });
}

// A valid AgentScratchpad: every field is ASCII so the anchored rendering stays
// UTF-8 valid. Checklist ids/texts are ASCII too.
rc::Gen<AgentScratchpad> gen_scratchpad() {
    return rc::gen::map(
        rc::gen::tuple(ascii_string(), ascii_string(),
                       rc::gen::container<std::vector<std::string>>(ascii_string()),
                       rc::gen::container<std::vector<std::string>>(ascii_string()),
                       ascii_string()),
        [](const std::tuple<std::string, std::string, std::vector<std::string>,
                            std::vector<std::string>, std::string>& t) {
            AgentScratchpad pad;
            pad.active_objective = std::get<0>(t);
            pad.current_hypothesis = std::get<1>(t);
            pad.verified_facts = std::get<2>(t);
            pad.failed_approaches_do_not_repeat = std::get<3>(t);
            pad.next_immediate_action = std::get<4>(t);
            return pad;
        });
}

// Module state snapshots: a list of (id, Json) pairs, all ASCII.
rc::Gen<std::vector<std::pair<std::string, Json>>> gen_snapshots() {
    return rc::gen::container<std::vector<std::pair<std::string, Json>>>(
        rc::gen::pair(ascii_string(), rc::gen::map(ascii_string(), [](std::string s) {
                          return Json(std::move(s));
                      })));
}

// ActionResult with the domain invariant: error_code empty exactly when success.
rc::Gen<ActionResult> gen_action_result(rc::Gen<std::string> output_gen) {
    return rc::gen::mapcat(
        rc::gen::arbitrary<bool>(),
        [output_gen](bool success) {
            auto fail_code = rc::gen::map(
                rc::gen::pair(rc::gen::elementOf(std::string("abcdefghijklmnopqrstuvwxyz")),
                              rc::gen::container<std::string>(rc::gen::elementOf(
                                  std::string("abcdefghijklmnopqrstuvwxyz0123456789_")))),
                [](const std::pair<char, std::string>& parts) {
                    return std::string(1, parts.first) + parts.second;
                });
            auto error_code = success ? rc::gen::just(std::string{}) : std::move(fail_code);
            return rc::gen::construct<ActionResult>(rc::gen::just(success), std::move(error_code),
                                                    output_gen,
                                                    rc::gen::arbitrary<std::uint64_t>());
        });
}

// A ToolInteraction whose llm_facing_output is drawn from `output_gen`, letting
// callers control whether outputs stay under or over the truncation budget.
rc::Gen<ToolInteraction> gen_interaction(rc::Gen<std::string> output_gen) {
    return rc::gen::construct<ToolInteraction>(ascii_string(),  // id
                                               ascii_string(),  // module
                                               ascii_string(),  // action
                                               ascii_object(),  // args
                                               gen_action_result(output_gen));
}

// Reconstruct the user-side call JSON that build_messages() emits for an
// interaction (module/action/args), so tail entries can be matched by content.
std::string expected_call_json(const ToolInteraction& it) {
    Json call = Json::object();
    call["module"] = it.module;
    call["action"] = it.action;
    call["args"] = it.args;
    return call.dump();
}

constexpr std::size_t kPrefixAndAnchor = 3;  // system prompt + schema + anchored block

}  // namespace

// ---------------------------------------------------------------------------
// Property 6: Segment ordering.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 6: build_messages() emits the pinned prefix
// (system prompt then recipe schema), then the anchored block, then the rolling
// tail in recorded order; the pinned-prefix messages equal the set system prompt
// and recipe schema.
// Validates: Requirements 2.1
TEST_CASE("Property 6: segment ordering", "[rapidcheck][context_condenser]") {
    rc::prop("pinned prefix, then anchor, then tail in recorded order", [] {
        const std::string system_prompt = *ascii_string();
        const std::string recipe_schema = *ascii_string();
        const AgentScratchpad pad = *gen_scratchpad();
        const auto snapshots = *gen_snapshots();
        // Keep outputs short so they are stored verbatim and ordering is checkable.
        TierLimits limits;
        const auto interactions = *rc::gen::container<std::vector<ToolInteraction>>(
            gen_interaction(ascii_string_of_length(8)));

        ContextCondenser condenser(limits);
        condenser.set_pinned_prefix(system_prompt, recipe_schema);
        condenser.set_anchored(pad, snapshots);
        for (const auto& it : interactions) {
            condenser.record_tool_cycle(it);
        }

        const std::vector<Message> messages = condenser.build_messages();

        // Pinned prefix: message[0] is the system prompt, message[1] the schema.
        RC_ASSERT(messages.size() >= kPrefixAndAnchor);
        RC_ASSERT(messages[0].role == Role::system);
        RC_ASSERT(messages[0].content == system_prompt);
        RC_ASSERT(messages[1].role == Role::system);
        RC_ASSERT(messages[1].content == recipe_schema);
        // Anchored block: message[2] is a single system message.
        RC_ASSERT(messages[2].role == Role::system);

        // Rolling tail: the last min(M, K) interactions as user/tool pairs, in
        // recorded order, directly after the three prefix/anchor messages.
        const std::size_t k = limits.rolling_tools;
        const std::size_t kept = std::min(interactions.size(), k);
        const std::size_t tail_msgs = messages.size() - kPrefixAndAnchor;
        RC_ASSERT(tail_msgs == kept * 2);
        for (std::size_t i = 0; i < kept; ++i) {
            const ToolInteraction& it = interactions[interactions.size() - kept + i];
            const Message& user = messages[kPrefixAndAnchor + i * 2];
            const Message& tool = messages[kPrefixAndAnchor + i * 2 + 1];
            RC_ASSERT(user.role == Role::user);
            RC_ASSERT(user.content == expected_call_json(it));
            RC_ASSERT(tool.role == Role::tool);
            RC_ASSERT(tool.content == it.result.llm_facing_output);
        }
    });
}

// ---------------------------------------------------------------------------
// Property 7: Rolling tail holds exactly the last K interactions.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 7: after recording M interactions the tail
// holds exactly the last min(M, K) in order and never exceeds K.
// Validates: Requirements 2.2
TEST_CASE("Property 7: rolling tail holds the last K interactions",
          "[rapidcheck][context_condenser]") {
    rc::prop("tail == last min(M, K) in recorded order, never exceeding K", [] {
        // Vary K across tiers (0..6) and the recorded count M independently.
        const std::size_t k = *rc::gen::inRange<std::size_t>(0, 7);
        TierLimits limits;
        limits.rolling_tools = k;

        // Distinct recognizable outputs so order is checkable; short so verbatim.
        const auto interactions = *rc::gen::container<std::vector<ToolInteraction>>(
            gen_interaction(ascii_string_of_length(8)));

        ContextCondenser condenser(limits);
        condenser.set_pinned_prefix("sys", "schema");
        condenser.set_anchored(AgentScratchpad{}, {});
        for (const auto& it : interactions) {
            condenser.record_tool_cycle(it);
        }

        const std::vector<Message> messages = condenser.build_messages();
        const std::size_t tail_pairs = (messages.size() - kPrefixAndAnchor) / 2;

        const std::size_t kept = std::min(interactions.size(), k);
        // Tail holds exactly min(M, K) pairs and never exceeds K.
        RC_ASSERT(tail_pairs == kept);
        RC_ASSERT(tail_pairs <= k);

        // Each kept pair corresponds to the matching tail-end recorded interaction.
        for (std::size_t i = 0; i < kept; ++i) {
            const ToolInteraction& it = interactions[interactions.size() - kept + i];
            const Message& user = messages[kPrefixAndAnchor + i * 2];
            const Message& tool = messages[kPrefixAndAnchor + i * 2 + 1];
            RC_ASSERT(user.content == expected_call_json(it));
            RC_ASSERT(tool.content == it.result.llm_facing_output);
        }
    });
}

// ---------------------------------------------------------------------------
// Property 8: Oversized outputs truncate with a recoverable spill.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 8: outputs over tool_output_chars yield a
// bounded tail view embedding a spill ref whose resolve_spill(ref) returns the
// full text; shorter outputs are stored verbatim with no spill.
// Validates: Requirements 2.3
TEST_CASE("Property 8: oversized outputs truncate with a recoverable spill",
          "[rapidcheck][context_condenser]") {
    rc::prop("over-budget output spills recoverably; under-budget stored verbatim", [] {
        // A small, explicit budget keeps generated outputs manageable while still
        // straddling the boundary.
        TierLimits limits;
        limits.tool_output_chars = *rc::gen::inRange<std::size_t>(8, 64);
        limits.rolling_tools = 2;

        const bool oversized = *rc::gen::arbitrary<bool>();
        // Build an output either strictly under/at budget or strictly over it.
        const std::size_t len =
            oversized
                ? *rc::gen::inRange<std::size_t>(limits.tool_output_chars + 1,
                                                 limits.tool_output_chars + 200)
                : *rc::gen::inRange<std::size_t>(0, limits.tool_output_chars + 1);
        const std::string output = *ascii_string_of_length(len);

        ToolInteraction it = *gen_interaction(rc::gen::just(output));
        it.result.success = true;         // keep the ActionResult invariant simple
        it.result.error_code.clear();

        ContextCondenser condenser(limits);
        condenser.set_pinned_prefix("sys", "schema");
        condenser.set_anchored(AgentScratchpad{}, {});
        condenser.record_tool_cycle(it);

        const std::vector<Message> messages = condenser.build_messages();
        RC_ASSERT(messages.size() == kPrefixAndAnchor + 2);  // one user/tool pair
        const std::string& view = messages[kPrefixAndAnchor + 1].content;

        if (output.size() > limits.tool_output_chars) {
            // The marker embeds a `ref=spill:N` token; extract it.
            const std::string needle = "ref=spill:";
            const std::size_t marker = view.find(needle);
            RC_ASSERT(marker != std::string::npos);
            const std::size_t ref_start = marker + 4;  // skip "ref="
            const std::size_t ref_end = view.find(']', ref_start);
            RC_ASSERT(ref_end != std::string::npos);
            const std::string ref = view.substr(ref_start, ref_end - ref_start);

            // resolve_spill(ref) returns the original full text.
            const std::string* full = condenser.resolve_spill(ref);
            RC_ASSERT(full != nullptr);
            RC_ASSERT(*full == output);

            // The stored view is bounded: head+tail budget plus the marker length.
            const std::string marker_text =
                "... [spilled " + std::to_string(output.size()) + " chars, ref=" + ref + "] ...";
            RC_ASSERT(view.size() <= limits.tool_output_chars + marker_text.size());
        } else {
            // Short output stored verbatim, no spill minted.
            RC_ASSERT(view == output);
            RC_ASSERT(condenser.resolve_spill("spill:0") == nullptr);
        }
    });
}

// ---------------------------------------------------------------------------
// Property 9: Wipe preserves the prefix, refreshes the anchor, clears the tail.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 9: after condense() the pinned prefix is
// unchanged, the anchored block equals the latest scratchpad/snapshot rendering,
// and the rolling tail is empty.
// Validates: Requirements 2.4
TEST_CASE("Property 9: wipe preserves prefix, refreshes anchor, clears tail",
          "[rapidcheck][context_condenser]") {
    rc::prop("condense() keeps prefix, anchors the latest inputs, empties the tail", [] {
        const std::string system_prompt = *ascii_string();
        const std::string recipe_schema = *ascii_string();
        const AgentScratchpad pad_a = *gen_scratchpad();
        const auto snaps_a = *gen_snapshots();
        const AgentScratchpad pad_b = *gen_scratchpad();
        const auto snaps_b = *gen_snapshots();

        TierLimits limits;
        limits.rolling_tools = 4;
        const auto interactions = *rc::gen::container<std::vector<ToolInteraction>>(
            gen_interaction(ascii_string_of_length(8)));

        ContextCondenser condenser(limits);
        condenser.set_pinned_prefix(system_prompt, recipe_schema);
        condenser.set_anchored(pad_a, snaps_a);
        for (const auto& it : interactions) {
            condenser.record_tool_cycle(it);
        }
        const std::vector<Message> before = condenser.build_messages();

        // Set the LATEST anchored inputs, then wipe.
        condenser.set_anchored(pad_b, snaps_b);
        condenser.condense();
        const std::vector<Message> after = condenser.build_messages();

        // Pinned prefix unchanged (still the system prompt + recipe schema).
        RC_ASSERT(after.size() == kPrefixAndAnchor);  // prefix + anchor, no tail
        RC_ASSERT(after[0].content == system_prompt);
        RC_ASSERT(after[0].content == before[0].content);
        RC_ASSERT(after[1].content == recipe_schema);
        RC_ASSERT(after[1].content == before[1].content);

        // Anchored block reflects the LATEST inputs: equal to a fresh condenser
        // that only did set_pinned_prefix + set_anchored(pad_b, snaps_b).
        ContextCondenser reference(limits);
        reference.set_pinned_prefix(system_prompt, recipe_schema);
        reference.set_anchored(pad_b, snaps_b);
        const std::vector<Message> ref_messages = reference.build_messages();
        RC_ASSERT(ref_messages.size() == kPrefixAndAnchor);
        RC_ASSERT(after[2].content == ref_messages[2].content);
        RC_ASSERT(after[2].role == ref_messages[2].role);

        // Rolling tail empty: no messages past the anchor.
        RC_ASSERT(after.size() == kPrefixAndAnchor);
    });
}

// ---------------------------------------------------------------------------
// Property 10: Condense threshold is a monotone boundary.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 10: should_condense() is true exactly when
// estimate_prompt_tokens() >= the tier's condense_threshold.
// Validates: Requirements 2.6
TEST_CASE("Property 10: condense threshold is a monotone boundary",
          "[rapidcheck][context_condenser]") {
    rc::prop("should_condense() == (estimate_prompt_tokens() >= condense_threshold)", [] {
        // Vary the threshold small enough that varied prompt sizes straddle it.
        TierLimits limits;
        limits.condense_threshold = *rc::gen::inRange<std::uint32_t>(1, 400);
        limits.rolling_tools = *rc::gen::inRange<std::size_t>(0, 6);

        // Vary prompt sizes so both sides of the boundary are exercised: large
        // system prompt/schema plus a varying number of interactions.
        const std::string system_prompt = *ascii_string_of_length(*rc::gen::inRange<std::size_t>(0, 800));
        const std::string recipe_schema = *ascii_string_of_length(*rc::gen::inRange<std::size_t>(0, 800));
        const auto interactions = *rc::gen::container<std::vector<ToolInteraction>>(
            gen_interaction(ascii_string_of_length(16)));

        ContextCondenser condenser(limits);
        condenser.set_pinned_prefix(system_prompt, recipe_schema);
        condenser.set_anchored(*gen_scratchpad(), *gen_snapshots());
        for (const auto& it : interactions) {
            condenser.record_tool_cycle(it);
        }

        const std::uint64_t tokens = condenser.estimate_prompt_tokens();
        RC_ASSERT(condenser.should_condense() == (tokens >= limits.condense_threshold));
    });
}

// ---------------------------------------------------------------------------
// Property 14: Behavior follows tier limits, not hardcoded constants.
// ---------------------------------------------------------------------------
// Feature: m4-agent-loop, Property 14: two tiers differing in rolling_tools /
// condense_threshold change the tail cap and should_condense() boundary to match
// the selected tier.
// Validates: Requirements 4.4
TEST_CASE("Property 14: behavior follows tier limits, not hardcoded constants",
          "[rapidcheck][context_condenser]") {
    rc::prop("tail cap and condense boundary track each tier's own limits", [] {
        // CPU tier: rolling_tools=2, threshold=2048. GPU tier: rolling_tools=4,
        // threshold=6144. Both from the real tier table so no constant is baked in.
        const TierLimits cpu =
            RuntimeTierConfig::for_profile(ComputeProfile::cpu_low_spec_edge).limits;
        const TierLimits gpu =
            RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram).limits;
        RC_ASSERT(cpu.rolling_tools != gpu.rolling_tools);
        RC_ASSERT(cpu.condense_threshold != gpu.condense_threshold);

        // Record the same M > max(K) interactions into both condensers.
        const std::size_t max_k = std::max(cpu.rolling_tools, gpu.rolling_tools);
        const std::size_t count = *rc::gen::inRange<std::size_t>(max_k + 1, max_k + 8);
        const auto interactions = *rc::gen::container<std::vector<ToolInteraction>>(
            count, gen_interaction(ascii_string_of_length(8)));

        const auto tail_pairs = [&](const TierLimits& limits) {
            ContextCondenser condenser(limits);
            condenser.set_pinned_prefix("sys", "schema");
            condenser.set_anchored(AgentScratchpad{}, {});
            for (const auto& it : interactions) {
                condenser.record_tool_cycle(it);
            }
            const std::vector<Message> messages = condenser.build_messages();
            return (messages.size() - kPrefixAndAnchor) / 2;
        };

        // Each condenser caps its tail at ITS OWN rolling_tools.
        RC_ASSERT(tail_pairs(cpu) == cpu.rolling_tools);
        RC_ASSERT(tail_pairs(gpu) == gpu.rolling_tools);

        // The should_condense boundary tracks each tier's own condense_threshold.
        // Build a single prompt and feed it to both tiers; the only difference in
        // the decision comes from the per-tier threshold, never a hardcoded limit.
        // Size the prompt so its footprint straddles the two thresholds: between
        // lo*4 and hi*4 chars yields a token count between the two thresholds, so
        // the lower-threshold tier condenses while the higher-threshold tier does
        // not (the anchor overhead is identical for both, so it cancels out of the
        // comparison between tiers).
        const std::uint32_t lo = std::min(cpu.condense_threshold, gpu.condense_threshold);
        const std::uint32_t hi = std::max(cpu.condense_threshold, gpu.condense_threshold);
        const std::uint32_t mid = lo + (hi - lo) / 2;
        const std::string big_prompt = *ascii_string_of_length(static_cast<std::size_t>(mid) * 4);

        // Both condensers see the IDENTICAL prompt/anchor, so their estimated
        // footprints are equal; only the threshold differs.
        ContextCondenser cpu_condenser(cpu);
        cpu_condenser.set_pinned_prefix(big_prompt, "");
        cpu_condenser.set_anchored(AgentScratchpad{}, {});
        ContextCondenser gpu_condenser(gpu);
        gpu_condenser.set_pinned_prefix(big_prompt, "");
        gpu_condenser.set_anchored(AgentScratchpad{}, {});

        const std::uint64_t cpu_tokens = cpu_condenser.estimate_prompt_tokens();
        const std::uint64_t gpu_tokens = gpu_condenser.estimate_prompt_tokens();
        RC_ASSERT(cpu_tokens == gpu_tokens);  // same inputs -> same footprint

        // Each tier's decision agrees with ITS OWN threshold against that footprint.
        RC_ASSERT(cpu_condenser.should_condense() == (cpu_tokens >= cpu.condense_threshold));
        RC_ASSERT(gpu_condenser.should_condense() == (gpu_tokens >= gpu.condense_threshold));
    });
}
