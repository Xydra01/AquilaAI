#pragma once

// ContextStrategy (M5 task 11, Req 9 / D14) -- the kept interface the three
// context-management strategies implement so the Req 9 bake-off can score them on
// equal footing and the WINNER becomes M6's ContextCondenser driver.
//
// Why this exists: the GPU proof established that Qwen 3.5 (recurrent/M-RoPE)
// cannot do a mid-sequence KV rollback (see Req 3.6 and
// tests/live/llama_backend_live_test.cpp). That is the exact operation the
// original R6 KV-wipe condenser depended on. Rather than pick a replacement by
// argument, M5 implements three strategies behind THIS interface and lets measured
// task accuracy on the real model decide (D14):
//   - KvRollbackStrategy  (control): the original mid-sequence rollback path;
//                          typed-fails on Qwen 3.5, valid on plain-RoPE.
//   - EoCCStrategy        (End-of-Context Compaction): grow to a threshold, then
//                          condense the message list + rebuild via a full reset.
//   - SacStrategy         (Single-Action-per-Context): a fresh context per action,
//                          fed an aggressively summarized state each turn.
//
// All three drive the SAME M5 LlamaCppBackend (Req 9.7) through IInferenceBackend;
// they differ only in HOW they manage the context across turns.

#include "aquila/inference/backend.hpp"
#include "aquila/types/message.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace aquila {

// Observability the bake-off harness reads to score a strategy (Req 9.3). Counters
// are cumulative over the strategy's lifetime (one agent task).
struct StrategyStats {
    std::uint64_t tokens_decoded = 0;   // prompt/prefill + generation tokens fed to the model
    std::uint64_t turns = 0;            // add_turn + next_action cycles
    std::uint64_t compactions = 0;      // EoCC-style condense events
    std::uint64_t resets = 0;           // full-context resets (rollback_to(0) + rebuild)
    std::uint64_t typed_failures = 0;   // typed GenerationResult/LlamaError failures survived
};

// A context-management policy layered on an IInferenceBackend. One instance drives
// one agent task; it owns the logical message list and decides when/how to condense
// or reset so the backend's context stays within budget without losing task-
// relevant information.
class ContextStrategy {
public:
    virtual ~ContextStrategy() = default;

    // The pinned, immutable prefix (system prompt + action schema, R6 [0..P]). Set
    // once at the start of a task, before any turns.
    virtual void set_prefix(IInferenceBackend& backend,
                            const std::vector<Message>& prefix) = 0;

    // Add one turn (a user input or a tool result) to the managed context. The
    // strategy decides whether this triggers a condense/reset.
    virtual void add_turn(IInferenceBackend& backend, const Message& turn) = 0;

    // Produce the next action-call against the current managed context. The strategy
    // is responsible for presenting the backend a context it can actually decode
    // (e.g. it must NOT ask a Qwen 3.5 backend to resume after a mid-sequence wipe).
    virtual GenerationResult next_action(IInferenceBackend& backend,
                                         const GenerationParams& params,
                                         const TokenCallback& on_token) = 0;

    [[nodiscard]] virtual StrategyStats stats() const = 0;
    [[nodiscard]] virtual std::string_view name() const = 0;
};

}  // namespace aquila