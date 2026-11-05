#pragma once

// KvRollbackStrategy (M5 task 11.2, Req 9) -- the CONTROL strategy: the original
// R6 design that pins a prefix and does a MID-SEQUENCE rollback_to(P) on a wipe.
// On Qwen 3.5 (recurrent/M-RoPE) the wipe's next decode typed-fails (Req 3.6); the
// strategy catches that, counts it, and recovers with a full reset so the task can
// continue -- but every forced reset is the behavior the bake-off penalizes. On a
// plain-RoPE model this is the cheap, correct prefix-reuse path.

#include "aquila/context/context_strategy.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace aquila {

class KvRollbackStrategy final : public ContextStrategy {
public:
    // condense_after_turns: wipe the tail back to the prefix after this many turns.
    explicit KvRollbackStrategy(std::size_t condense_after_turns = 4);

    void set_prefix(IInferenceBackend& backend, const std::vector<Message>& prefix) override;
    void add_turn(IInferenceBackend& backend, const Message& turn) override;
    GenerationResult next_action(IInferenceBackend& backend, const GenerationParams& params,
                                 const TokenCallback& on_token) override;
    [[nodiscard]] StrategyStats stats() const override { return stats_; }
    [[nodiscard]] std::string_view name() const override { return "kv_rollback"; }

private:
    void full_reset_rebuild(IInferenceBackend& backend);

    std::size_t condense_after_turns_;
    std::size_t checkpoint_ = 0;             // P: end of the pinned prefix
    std::size_t turns_since_wipe_ = 0;
    std::vector<Message> prefix_;            // retained so a full reset can rebuild
    std::vector<Message> tail_;              // turns since the last wipe
    StrategyStats stats_;
};

}  // namespace aquila