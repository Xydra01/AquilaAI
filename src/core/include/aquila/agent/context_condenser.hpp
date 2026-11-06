#pragma once

#include "aquila/agent/runtime_tier.hpp"
#include "aquila/types/message.hpp"
#include "aquila/types/scratchpad.hpp"
#include "aquila/types/tool_interaction.hpp"

#include <cstdint>
#include <deque>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace aquila {

// Full text of a spilled (oversized) tool output, reachable by reference (R8).
struct SpillEntry {
    std::string ref;        // stable handle embedded in the truncated view
    std::string full_text;
};

// Context compaction strategy (M5 bake-off / D14).
enum class CondenserStrategy {
    eocc,   // End-of-Context Compaction: accumulates turns in rolling tail up to rolling_tools
    sac     // Single-Action-per-Context: fresh minimal context per action, prior turns folded into running summary (Llama bake-off winner)
};

// Three-segment prompt assembler (Req 2, R6, R8):
//   pinned prefix  -> system prompt + active recipe schema (never evicted)
//   anchored block -> a snapshot of the scratchpad + module state snapshots
//   rolling tail   -> the last K tool interactions (or single turn under SAC), oversized outputs spilled
// All thresholds come from TierLimits; the condenser hardcodes nothing (Req 4.4).
class ContextCondenser {
public:
    explicit ContextCondenser(TierLimits limits, CondenserStrategy strategy = CondenserStrategy::sac);

    [[nodiscard]] CondenserStrategy strategy() const noexcept { return strategy_; }
    void set_strategy(CondenserStrategy strategy) noexcept { strategy_ = strategy; }

    // Returns the current running summary folded under SAC strategy (or empty for EoCC).
    [[nodiscard]] const std::string& running_summary() const noexcept { return running_summary_; }

    // Pinned prefix [0..P]: system prompt + active recipe schema. Set once; never
    // evicted (Req 2.1). Schema text is the rendered action schema for the recipe.
    void set_pinned_prefix(std::string system_prompt, std::string recipe_schema);

    // Anchored block [P+1..S]: a snapshot of the scratchpad + module state snapshots.
    // Refreshed on wipe; otherwise stable (Req 2.1, 2.4).
    void set_anchored(const AgentScratchpad& scratchpad,
                      const std::vector<std::pair<std::string, Json>>& module_snapshots);

    // Rolling tail [S+1..end]: records one interaction, evicting the oldest when the
    // tail already holds K = limits.rolling_tools entries (Req 2.2). Oversized outputs
    // are stored head+tail-truncated with the full text spilled (Req 2.3).
    void record_tool_cycle(const ToolInteraction& interaction);

    // Appends a corrective/guidance user message to the tail region without a tool
    // cycle (parse-failure recovery and hook on_failure_instruction).
    void push_guidance(std::string text);

    // Assembles the prompt: pinned prefix, then anchored block, then rolling tail,
    // in that order (Req 2.1).
    [[nodiscard]] std::vector<Message> build_messages() const;

    // ceil(chars/4) via estimate_tokens over build_messages(); agrees with Python's
    // estimate_messages_tokens within rounding (Req 2.5).
    [[nodiscard]] std::uint64_t estimate_prompt_tokens() const;

    // True once the assembled footprint reaches limits.condense_threshold (Req 2.6).
    [[nodiscard]] bool should_condense() const;

    // Wipe: pinned prefix unchanged, anchored block refreshed from the latest
    // set_anchored() inputs, rolling tail cleared (Req 2.4).
    void condense();

    // Side-buffer lookup for a spilled output (R8).
    [[nodiscard]] const std::string* resolve_spill(const std::string& ref) const;

private:
    [[nodiscard]] std::string head_tail_truncate(const std::string& text, std::string& out_ref);

    // Renders the cached scratchpad + module snapshots into `anchored_`. Shared by
    // set_anchored() and condense() so the wipe refresh is byte-identical to the
    // most recent set_anchored() rendering (Req 2.4).
    void render_anchored();

    TierLimits limits_;
    CondenserStrategy strategy_ = CondenserStrategy::sac;
    std::string running_summary_;
    std::string system_prompt_;
    std::string recipe_schema_;
    Message anchored_;                         // rendered scratchpad + snapshots
    // Raw inputs behind `anchored_`, retained so condense() can re-render the block
    // from the latest set_anchored() inputs without the caller re-supplying them.
    AgentScratchpad anchored_scratchpad_;
    std::vector<std::pair<std::string, Json>> anchored_snapshots_;
    std::deque<ToolInteraction> tail_;         // ring buffer, cap = rolling_tools
    std::vector<std::string> guidance_;        // pending corrective messages
    std::unordered_map<std::string, std::string> spill_;  // ref -> full_text
    std::uint64_t spill_seq_ = 0;
};

}  // namespace aquila
