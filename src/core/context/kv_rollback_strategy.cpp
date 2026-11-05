// KvRollbackStrategy implementation (M5 task 11.2, Req 9 control strategy).

#include "aquila/context/kv_rollback_strategy.hpp"

#include <stdexcept>
#include <utility>

namespace aquila {

KvRollbackStrategy::KvRollbackStrategy(std::size_t condense_after_turns)
    : condense_after_turns_(condense_after_turns == 0 ? 1 : condense_after_turns) {}

void KvRollbackStrategy::set_prefix(IInferenceBackend& backend,
                                    const std::vector<Message>& prefix) {
    prefix_ = prefix;
    backend.rollback_to(0);
    for (const Message& m : prefix_) {
        backend.append(m);
    }
    checkpoint_ = backend.mark_checkpoint();  // P: end of the pinned prefix
    tail_.clear();
    turns_since_wipe_ = 0;
}

void KvRollbackStrategy::full_reset_rebuild(IInferenceBackend& backend) {
    // The M-RoPE-safe recovery: clear everything and re-decode prefix + the turns
    // we still want to keep. Counted as a reset (the behavior the bake-off
    // penalizes relative to a cheap mid-sequence wipe).
    backend.rollback_to(0);
    for (const Message& m : prefix_) {
        backend.append(m);
    }
    checkpoint_ = backend.mark_checkpoint();
    for (const Message& m : tail_) {
        backend.append(m);
    }
    ++stats_.resets;
}

void KvRollbackStrategy::add_turn(IInferenceBackend& backend, const Message& turn) {
    // Periodic wipe: the ORIGINAL R6 move is a mid-sequence rollback to the prefix
    // checkpoint, keeping the prefix KV and re-decoding only new tail. On Qwen 3.5
    // the NEXT decode after that wipe typed-fails (Req 3.6); we catch it and fall
    // back to a full reset so the task survives.
    if (turns_since_wipe_ >= condense_after_turns_) {
        tail_.clear();  // the wipe discards the rolling tail (prefix is the memory)
        try {
            backend.rollback_to(checkpoint_);  // mid-sequence wipe to P
            // Probe the resume path by appending the new turn; on Qwen 3.5 this is
            // where llama_decode reports the inconsistent-position failure.
            backend.append(turn);
            tail_.push_back(turn);
        } catch (const std::exception&) {
            // Typed failure (M-RoPE partial-rollback is unsupported): recover with a
            // full reset, then land the turn cleanly.
            ++stats_.typed_failures;
            full_reset_rebuild(backend);
            backend.append(turn);
            tail_.push_back(turn);
        }
        turns_since_wipe_ = 0;
    } else {
        backend.append(turn);
        tail_.push_back(turn);
    }
    ++turns_since_wipe_;
    ++stats_.turns;
}

GenerationResult KvRollbackStrategy::next_action(IInferenceBackend& backend,
                                                 const GenerationParams& params,
                                                 const TokenCallback& on_token) {
    const GenerationResult r = backend.generate(params, on_token);
    stats_.tokens_decoded += r.prompt_tokens + r.completion_tokens;
    if (!r.ok) {
        ++stats_.typed_failures;
    }
    return r;
}

}  // namespace aquila