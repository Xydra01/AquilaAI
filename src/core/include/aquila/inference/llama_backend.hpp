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

#include <cstddef>

namespace aquila {

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
    // Build the per-call sampler chain from GenerationParams in the design's order:
    // penalties -> (top_k -> top_p: not present on GenerationParams, see .cpp) ->
    // temp -> grammar (when a constraint is set) -> dist(seed), OR a bare greedy
    // sampler when temperature == 0 (deterministic, Req 4.5). Returns a SamplerPtr
    // owning the WHOLE chain (one llama_sampler*); adding a child transfers its
    // ownership to the chain, so the chain's deleter frees everything exactly once.
    //
    // `grammar_null_out` is set to true when a constraint IS set but the grammar
    // sampler came back NULL (unparseable grammar): generate() maps that to
    // error_code="invalid_request" WITHOUT running the loop. On that path the
    // returned SamplerPtr is null.
    [[nodiscard]] SamplerPtr build_sampler(const GenerationParams& params,
                                           bool& grammar_null_out);

    LlamaConfig cfg_;
    LlamaSession session_;
    GrammarFactory grammar_;
};

#endif  // AQUILA_HAS_LLAMACPP

}  // namespace aquila
