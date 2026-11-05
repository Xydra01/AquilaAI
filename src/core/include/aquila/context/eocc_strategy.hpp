#pragma once

// EoCCStrategy (M5 task 11.2, Req 9) -- End-of-Context Compaction. Grows the
// managed message list until the estimated footprint reaches a threshold (default
// ~16K tokens, the NVIDIA "you don't need long context" regime), then condenses the
// older turns into a summary and REBUILDS the context with a full reset
// (rollback_to(0)). No mid-sequence KV surgery, so it is M-RoPE-safe by
// construction. Relies on the backend's prefix staying stable across rebuilds.

#include "aquila/context/context_strategy.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace aquila {

class EoCCStrategy final : public ContextStrategy {
public:
    // compact_threshold_tokens: condense when the estimate reaches this.
    // keep_recent_turns: how many of the most recent turns to keep verbatim after a
    // compaction (the rest fold into the running summary).
    explicit EoCCStrategy(std::uint64_t compact_threshold_tokens = 16000,
                          std::size_t keep_recent_turns = 4);

    void set_prefix(IInferenceBackend& backend, const std::vector<Message>& prefix) override;
    void add_turn(IInferenceBackend& backend, const Message& turn) override;
    GenerationResult next_action(IInferenceBackend& backend, const GenerationParams& params,
                                 const TokenCallback& on_token) override;
    [[nodiscard]] StrategyStats stats() const override { return stats_; }
    [[nodiscard]] std::string_view name() const override { return "eocc"; }

private:
    [[nodiscard]] std::uint64_t estimate_tokens() const;
    void compact_and_rebuild(IInferenceBackend& backend);
    void rebuild(IInferenceBackend& backend);

    std::uint64_t compact_threshold_tokens_;
    std::size_t keep_recent_turns_;
    std::vector<Message> prefix_;
    std::string summary_;          // folded older turns (grows, but bounded by compaction)
    std::vector<Message> turns_;   // verbatim turns since the last compaction
    StrategyStats stats_;
};

}  // namespace aquila