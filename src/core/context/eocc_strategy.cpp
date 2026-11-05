// EoCCStrategy implementation (M5 task 11.2, Req 9 End-of-Context Compaction).

#include "aquila/context/eocc_strategy.hpp"

#include <algorithm>
#include <utility>

namespace aquila {

EoCCStrategy::EoCCStrategy(std::uint64_t compact_threshold_tokens,
                           std::size_t keep_recent_turns)
    : compact_threshold_tokens_(compact_threshold_tokens),
      keep_recent_turns_(keep_recent_turns) {}

namespace {
// ceil(chars/4), the same cheap heuristic ContextCondenser::estimate_prompt_tokens
// uses so the two agree within rounding (M4 Req 2.5).
std::uint64_t est_tokens(const std::string& s) {
    return (static_cast<std::uint64_t>(s.size()) + 3) / 4;
}
std::uint64_t est_tokens(const Message& m) {
    std::uint64_t n = est_tokens(m.content);
    for (const std::string& img : m.images) n += est_tokens(img);
    return n;
}
}  // namespace

std::uint64_t EoCCStrategy::estimate_tokens() const {
    std::uint64_t n = 0;
    for (const Message& m : prefix_) n += est_tokens(m);
    n += est_tokens(summary_);
    for (const Message& m : turns_) n += est_tokens(m);
    return n;
}

void EoCCStrategy::rebuild(IInferenceBackend& backend) {
    // Full reset + re-decode: prefix, then the running summary (as a system-style
    // note), then the verbatim recent turns. M-RoPE-safe (no mid-sequence wipe).
    backend.rollback_to(0);
    for (const Message& m : prefix_) {
        backend.append(m);
    }
    if (!summary_.empty()) {
        backend.append(Message{Role::system, "Summary of earlier progress:\n" + summary_, {}});
    }
    for (const Message& m : turns_) {
        backend.append(m);
    }
    ++stats_.resets;
}

void EoCCStrategy::compact_and_rebuild(IInferenceBackend& backend) {
    // Fold all but the most recent keep_recent_turns_ turns into the summary, then
    // rebuild. This is a deterministic, extractive fold (role-tagged concatenation);
    // a model-driven summarization can replace it later -- the bake-off measures
    // whether even this cheap compaction preserves enough to finish the task.
    if (turns_.size() > keep_recent_turns_) {
        const std::size_t fold_count = turns_.size() - keep_recent_turns_;
        std::string folded = summary_;
        for (std::size_t i = 0; i < fold_count; ++i) {
            folded += "\n[";
            folded += to_string(turns_[i].role);
            folded += "] ";
            folded += turns_[i].content;
        }
        summary_ = std::move(folded);
        turns_.erase(turns_.begin(), turns_.begin() + static_cast<std::ptrdiff_t>(fold_count));
    }
    ++stats_.compactions;
    rebuild(backend);
}

void EoCCStrategy::set_prefix(IInferenceBackend& backend, const std::vector<Message>& prefix) {
    prefix_ = prefix;
    summary_.clear();
    turns_.clear();
    rebuild(backend);
    stats_.resets = 0;  // the initial build is not a condense-driven reset
}

void EoCCStrategy::add_turn(IInferenceBackend& backend, const Message& turn) {
    turns_.push_back(turn);
    ++stats_.turns;
    if (estimate_tokens() >= compact_threshold_tokens_) {
        compact_and_rebuild(backend);
    } else {
        backend.append(turn);  // grow in place until the threshold is hit
    }
}

GenerationResult EoCCStrategy::next_action(IInferenceBackend& backend,
                                           const GenerationParams& params,
                                           const TokenCallback& on_token) {
    const GenerationResult r = backend.generate(params, on_token);
    stats_.tokens_decoded += r.prompt_tokens + r.completion_tokens;
    if (!r.ok) ++stats_.typed_failures;
    return r;
}

}  // namespace aquila