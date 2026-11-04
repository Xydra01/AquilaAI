#pragma once

// Scripted IInferenceBackend test double (M4, Req 8.3). Lets a unit test drive
// the AgentLoop deterministically with no network: `generate` pops the next
// scripted GenerationResult in order, while `append` and the KV ops record the
// context so a test can assert on it. It mirrors the Ollama scaffold's
// `supports_kv_reuse() == false`, so KV ops degrade to tracking the message
// list by position (a checkpoint is a context size; rollback truncates to it).

#include "aquila/inference/backend.hpp"
#include "aquila/types/message.hpp"

#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

namespace aquila::test {

class ReplayBackend final : public IInferenceBackend {
public:
    explicit ReplayBackend(std::vector<GenerationResult> scripted,
                           ComputeProfile profile = ComputeProfile::cpu_low_spec_edge)
        : scripted_(std::move(scripted)), profile_(profile) {}

    // Records the message for later assertions (mirrors the Ollama scaffold,
    // which keeps the context as a message list and resends it in full).
    void append(const Message& message) override { context_.push_back(message); }

    // A checkpoint is a position in the context (its current size), readable
    // from a const method as the interface requires.
    [[nodiscard]] std::size_t mark_checkpoint() const override { return context_.size(); }

    // Truncates the recorded context back to `checkpoint`. Throws
    // std::out_of_range if the checkpoint is past the current end, matching the
    // IInferenceBackend contract.
    void rollback_to(std::size_t checkpoint) override {
        if (checkpoint > context_.size()) {
            throw std::out_of_range("ReplayBackend::rollback_to: checkpoint past end of context");
        }
        context_.resize(checkpoint);
    }

    // Pops the next scripted reply in order. Streams the scripted content and
    // thinking through a non-empty callback in a single chunk, honoring the
    // "return false => cancel" contract (a cancel yields error_code "cancelled"
    // and keeps whatever was emitted). Throws std::out_of_range when the script
    // is exhausted so a missing reply fails loudly and deterministically.
    GenerationResult generate(const GenerationParams& /*params*/, const TokenCallback& on_token) override {
        if (next_ >= scripted_.size()) {
            throw std::out_of_range("ReplayBackend::generate: scripted replies exhausted");
        }
        const GenerationResult reply = scripted_[next_];
        ++next_;
        ++generate_calls_;

        if (on_token && reply.ok && (!reply.content.empty() || !reply.thinking.empty())) {
            if (!on_token(reply.content, reply.thinking)) {
                GenerationResult cancelled = reply;
                cancelled.ok = false;
                cancelled.error_code = "cancelled";
                cancelled.done_reason = "cancelled";
                return cancelled;
            }
        }
        return reply;
    }

    [[nodiscard]] ComputeProfile active_profile() const noexcept override { return profile_; }

    // Mirrors the Ollama scaffold: no KV reuse, so the loop resends the context.
    [[nodiscard]] bool supports_kv_reuse() const noexcept override { return false; }

    // --- test assertion accessors (not part of IInferenceBackend) ---

    [[nodiscard]] const std::vector<Message>& context() const noexcept { return context_; }
    [[nodiscard]] std::size_t generate_calls() const noexcept { return generate_calls_; }
    [[nodiscard]] std::size_t remaining() const noexcept { return scripted_.size() - next_; }
    [[nodiscard]] bool exhausted() const noexcept { return next_ >= scripted_.size(); }

private:
    std::vector<GenerationResult> scripted_;
    ComputeProfile profile_;
    std::vector<Message> context_;
    std::size_t next_ = 0;
    std::size_t generate_calls_ = 0;
};

}  // namespace aquila::test
