#pragma once

// SacStrategy (M5 task 11.2, Req 9) -- Single-Action-per-Context. Each action runs
// against a FRESH context: prefix + a running summary + the single current turn.
// Every next_action does a full reset (rollback_to(0)) and re-decodes that minimal
// context, so there is never any mid-sequence state to be inconsistent -- the
// M-RoPE constraint is dissolved by construction. The running summary is the only
// memory carried across actions, so summarization fidelity is load-bearing (the
// exact risk the bake-off measures).

#include "aquila/context/context_strategy.hpp"

#include <string>
#include <vector>

namespace aquila {

class SacStrategy final : public ContextStrategy {
public:
    SacStrategy() = default;

    void set_prefix(IInferenceBackend& backend, const std::vector<Message>& prefix) override;
    void add_turn(IInferenceBackend& backend, const Message& turn) override;
    GenerationResult next_action(IInferenceBackend& backend, const GenerationParams& params,
                                 const TokenCallback& on_token) override;
    [[nodiscard]] StrategyStats stats() const override { return stats_; }
    [[nodiscard]] std::string_view name() const override { return "sac"; }

private:
    void rebuild_minimal(IInferenceBackend& backend);

    std::vector<Message> prefix_;
    std::string summary_;          // compressed memory of all prior turns
    Message current_turn_;         // the single turn the next action responds to
    bool have_turn_ = false;
    StrategyStats stats_;
};

}  // namespace aquila