// SacStrategy implementation (M5 task 11.2, Req 9 Single-Action-per-Context).

#include "aquila/context/sac_strategy.hpp"

#include <utility>

namespace aquila {

void SacStrategy::rebuild_minimal(IInferenceBackend& backend) {
    // A FRESH context for every action: prefix + running summary + the single
    // current turn. Full reset, so there is never a mid-sequence state to be
    // inconsistent -- the Qwen 3.5 M-RoPE constraint is dissolved by construction.
    backend.rollback_to(0);
    for (const Message& m : prefix_) {
        backend.append(m);
    }
    if (!summary_.empty()) {
        backend.append(Message{Role::system, "State so far:\n" + summary_, {}});
    }
    if (have_turn_) {
        backend.append(current_turn_);
    }
    ++stats_.resets;
}

void SacStrategy::set_prefix(IInferenceBackend& backend, const std::vector<Message>& prefix) {
    prefix_ = prefix;
    summary_.clear();
    have_turn_ = false;
    backend.rollback_to(0);
    for (const Message& m : prefix_) {
        backend.append(m);
    }
}

void SacStrategy::add_turn(IInferenceBackend& /*backend*/, const Message& turn) {
    // The PREVIOUS current turn (if any) folds into the running summary before the
    // new turn replaces it -- SAC carries only the summary across actions.
    if (have_turn_) {
        summary_ += "\n[";
        summary_ += to_string(current_turn_.role);
        summary_ += "] ";
        summary_ += current_turn_.content;
    }
    current_turn_ = turn;
    have_turn_ = true;
    ++stats_.turns;
    // No backend append here; next_action rebuilds the minimal fresh context.
}

GenerationResult SacStrategy::next_action(IInferenceBackend& backend,
                                          const GenerationParams& params,
                                          const TokenCallback& on_token) {
    rebuild_minimal(backend);  // fresh context per action
    const GenerationResult r = backend.generate(params, on_token);
    stats_.tokens_decoded += r.prompt_tokens + r.completion_tokens;
    if (!r.ok) ++stats_.typed_failures;
    return r;
}

}  // namespace aquila