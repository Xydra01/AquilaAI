#pragma once

// LlamaCppBackend (M5): the IInferenceBackend linked directly against upstream
// llama.cpp. It makes the M2 KV interface real -- `mark_checkpoint` / `rollback_to`
// map onto llama.cpp sequence memory via LlamaSession (R6) -- and enforces the
// action-call JSON schema with GBNF via GrammarFactory (R14).
//
// Everything that touches the llama.cpp C API is guarded by `#if AQUILA_HAS_LLAMACPP`
// so this header + its TU still compile (as an empty TU) on the stub lanes
// (mingw-san / msvc-asan), where the backend is compiled out (see
// cmake/AquilaLlamaCpp.cmake). The macro is always defined by the `aquila_llamacpp`
// INTERFACE target (1 when built, 0 when stubbed).
//
// Task scope note (M5 task 4.1): construction + append + mark_checkpoint +
// rollback_to + active_profile + supports_kv_reuse are implemented here. The
// `generate` token loop (sampler chain + streaming + KV restore) is task 4.2 -- it
// is DECLARED here (it is a pure-virtual override, so the class must declare it) and
// given a compiling not-implemented stub in llama_backend.cpp (TODO(4.2)), so the
// class is concrete and a construction test can run.
//
// LlamaConfig is NOT redefined here: task 2.1 placed it in llama_session.hpp (the
// header this one includes) so LlamaSession's constructor and LlamaCppBackend share
// the exact same type with no circular include. The design sketches LlamaConfig in
// this header; the documented placement is llama_session.hpp for the 2.1 -> 4.1
// ordering.

#include "aquila/inference/backend.hpp"        // IInferenceBackend, GenerationParams, ...
#include "aquila/inference/grammar.hpp"        // GrammarFactory (guarded)
#include "aquila/inference/llama_session.hpp"  // LlamaConfig, LlamaSession (guarded)

#if AQUILA_HAS_LLAMACPP
#include <chat.h>
#endif

#include <algorithm>
#include <cstddef>
#include <string>
#include <string_view>

namespace aquila {

// Streaming splitter that cleanly separates `<think>...</think>` reasoning spans
// from user/parser-facing content without cutting partial `<think>` / `</think>`
// tags across token boundaries.
class ThinkStreamSplitter {
public:
    explicit ThinkStreamSplitter(bool start_in_think = false) : in_think_(start_in_think) {}

    void push(std::string_view piece, std::string& content_out, std::string& thinking_out) {
        buf_.append(piece);
        drain(false, content_out, thinking_out);
    }

    void flush(std::string& content_out, std::string& thinking_out) {
        drain(true, content_out, thinking_out);
    }

private:
    static constexpr std::string_view kOpenTag = "<think>";
    static constexpr std::string_view kCloseTag = "</think>";

    void drain(bool force_all, std::string& content_out, std::string& thinking_out) {
        while (!buf_.empty()) {
            if (skip_leading_newlines_ > 0) {
                if (buf_[0] == '\n') {
                    buf_.erase(0, 1);
                    --skip_leading_newlines_;
                    continue;
                }
                skip_leading_newlines_ = 0;
            }
            const std::string_view tag = in_think_ ? kCloseTag : kOpenTag;
            std::string& target = in_think_ ? thinking_out : content_out;

            const std::size_t hit = buf_.find(tag);
            if (hit != std::string::npos) {
                target.append(buf_.data(), hit);
                buf_.erase(0, hit + tag.size());
                skip_leading_newlines_ = in_think_ ? 2 : 1;
                in_think_ = !in_think_;
                continue;
            }

            if (force_all) {
                target.append(buf_);
                buf_.clear();
                break;
            }

            std::size_t hold = 0;
            const std::size_t max_check = std::min(buf_.size(), tag.size() - 1);
            for (std::size_t len = max_check; len >= 1; --len) {
                if (buf_.compare(buf_.size() - len, len, tag.data(), len) == 0) {
                    hold = len;
                    break;
                }
            }
            const std::size_t safe_len = buf_.size() - hold;
            if (safe_len > 0) {
                target.append(buf_.data(), safe_len);
                buf_.erase(0, safe_len);
            }
            break;
        }
    }

    bool in_think_ = false;
    int skip_leading_newlines_ = 0;
    std::string buf_;
};

[[nodiscard]] inline bool opener_starts_in_think(std::string_view opener) {
    const std::size_t open_pos = opener.rfind("<think>");
    if (open_pos == std::string_view::npos) {
        return false;
    }
    const std::size_t close_pos = opener.rfind("</think>");
    return close_pos == std::string_view::npos || close_pos < open_pos;
}

#if AQUILA_HAS_LLAMACPP

// The llama.cpp-backed IInferenceBackend (Req 2-6). Owns the model/context/KV
// (LlamaSession) and the schema->GBNF factory (GrammarFactory) on one logical
// thread (R2). Non-copyable / non-movable because LlamaSession is (it owns native
// handles and a logical KV position that must not be duplicated or relocated).
class LlamaCppBackend final : public IInferenceBackend {
public:
    // Loads the GGUF model and creates the context from `cfg` (model_path, n_ctx,
    // n_gpu_layers already derived from the tier by the caller: 0 for CPU tiers,
    // 999 for gpu_high_vram -- R16). Throws std::runtime_error on a load/creation
    // failure, never a half-built object (Req 2.1, 2.2).
    explicit LlamaCppBackend(LlamaConfig cfg);

    LlamaCppBackend(const LlamaCppBackend&) = delete;
    LlamaCppBackend& operator=(const LlamaCppBackend&) = delete;
    LlamaCppBackend(LlamaCppBackend&&) = delete;
    LlamaCppBackend& operator=(LlamaCppBackend&&) = delete;
    ~LlamaCppBackend() override = default;

    // Frame the single message by its role (model chat template, applied exactly
    // once by the backend) and decode it into the KV, advancing the position
    // (Req 3.1). A hard failure (context_overflow / decode_failed) propagates as a
    // LlamaError (the interface returns void, matching OllamaHttpBackend building
    // context eagerly).
    void append(const Message& message) override;

    // The current KV sequence position (tokens decoded so far) -- the checkpoint
    // value (Req 3.2).
    [[nodiscard]] std::size_t mark_checkpoint() const override;

    // Remove KV entries for [checkpoint, end) and reset the position (Req 3.3).
    // Throws std::out_of_range when checkpoint > the current end (Req 3.4, the M2
    // interface contract).
    void rollback_to(std::size_t checkpoint) override;

    // Generate a reply to the current context and leave the KV EXACTLY as it was on
    // entry (Req 6.4): the reply tokens are decoded to drive sampling, then trimmed
    // back to the pre-call position, so the caller decides what to keep. Builds a
    // per-call sampler chain (build_sampler), runs the token loop (sample ->
    // decode_one -> llama_token_to_piece -> stream via on_token), and maps every
    // outcome to the typed error vocabulary (stop / length / cancelled /
    // stream_stalled / decode_failed / context_overflow / invalid_request). Never
    // throws for a generation failure -- it returns a typed GenerationResult; the
    // KV restore runs on every exit path including an exception (Req 4, 5, 6).
    GenerationResult generate(const GenerationParams& params, const TokenCallback& on_token) override;

    [[nodiscard]] ComputeProfile active_profile() const noexcept override { return cfg_.profile; }
    [[nodiscard]] bool supports_kv_reuse() const noexcept override { return true; }

private:
    // Build the per-call sampling chain (penalties -> top_k -> top_p -> min_p ->
    // temp -> dist, or penalties -> greedy at temperature == 0) plus the optional
    // GBNF grammar sampler separated for grammar-based rejection sampling in
    // generate(): unconstrained sampling checks the single chosen token against
    // `grammar_out` (~microseconds) and only scans the full vocabulary if rejected.
    //
    // `grammar_null_out` is set to true when a constraint IS set but the grammar
    // sampler came back NULL (unparseable grammar): generate() maps that to
    // error_code="invalid_request" WITHOUT running the loop.
    [[nodiscard]] SamplerPtr build_sampler(const GenerationParams& params,
                                           bool& grammar_null_out,
                                           SamplerPtr& grammar_out);

    LlamaConfig cfg_;
    LlamaSession session_;
    GrammarFactory grammar_;
    common_chat_templates_ptr tmpls_;
};

#endif  // AQUILA_HAS_LLAMACPP

}  // namespace aquila
