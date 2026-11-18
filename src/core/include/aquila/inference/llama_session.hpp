#pragma once

// LlamaSession (M5): owns a llama.cpp model + context and the logical KV position,
// and implements the KV-aware primitives the IInferenceBackend contract needs
// (tokenize/decode, checkpoint via position(), rollback via llama_memory_seq_rm).
//
// Everything that touches the llama.cpp C API is guarded by `#if AQUILA_HAS_LLAMACPP`
// so this translation unit still compiles (as an empty TU) on the stub lanes
// (mingw-san / msvc-asan), where the backend is compiled out (see
// cmake/AquilaLlamaCpp.cmake). The macro is always defined by the `aquila_llamacpp`
// INTERFACE target (1 when built, 0 when stubbed).
//
// Task scope note (M5 task 2.1): this header declares the RAII wrappers, the
// LlamaBatch owning wrapper, LlamaConfig, and the full LlamaSession class; the
// constructor (model load + context creation) is implemented in 2.1. The
// tokenize/decode/position/rollback BODIES are task 2.2 -- here they are declared
// and the .cpp gives compiling placeholders that throw "not implemented" so a
// construction test can run without pulling in 2.2's logic.

#include "aquila/inference/backend.hpp"  // ComputeProfile (shared M2 value type)

#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#if AQUILA_HAS_LLAMACPP
#include <llama.h>
#endif
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
#include <mtmd.h>
#include <mtmd-helper.h>
#endif

namespace aquila {

// Configuration for constructing a LlamaSession / LlamaCppBackend.
//
// LlamaConfig lives HERE (not in llama_backend.hpp) on purpose: LlamaSession's
// constructor needs it, and llama_backend.hpp (task 4) does not exist yet. Putting
// it in a header task 4 already includes (llama_session.hpp) lets task 4's
// LlamaCppBackend reuse the exact same type with no circular include and no
// duplicate definition. The design sketches LlamaConfig in llama_backend.hpp; this
// is the documented, cleaner placement for the 2.1 -> 4.1 ordering.
struct LlamaConfig {
    std::string model_path;                                        // GGUF path
    std::string mmproj_path;                                       // Optional multimodal projector GGUF path
    ComputeProfile profile = ComputeProfile::cpu_low_spec_edge;
    std::uint32_t n_ctx = 16384;                                   // 16K CPU / 32K GPU default for Qwen 3.5
    std::int32_t n_gpu_layers = 0;                                 // 0 CPU tiers, 999 gpu_high_vram (R16)
    std::optional<std::uint32_t> n_threads;                        // default: llama.cpp's own (R17 seam)
    bool flash_attn = true;                                        // Enable FlashAttention on GPU (AUTO on CPU)
    bool kv_quant_q8 = true;                                       // Quantize K/V cache to Q8_0 on GPU
    bool auto_discover_mmproj = true;                              // Auto-discover companion mmproj*.gguf when mmproj_path is empty
    bool eager_load_mmproj = false;                                // Defer mtmd projector load until first multimodal turn when false
};

// Best-effort dimension-safe companion mmproj*.gguf resolver for a GGUF model path.
// Matches size tags (e.g. "4b" vs "9b") to avoid loading mismatched projectors.
[[nodiscard]] std::string discover_mmproj_for_model(const std::string& model_path);

#if AQUILA_HAS_LLAMACPP

// --- RAII handle wrappers (Req 2, R1: zero raw owning pointers) --------------
// Each llama.cpp C handle is owned by a unique_ptr with a noexcept custom deleter
// so it frees deterministically on scope exit / session destruction.

struct LlamaModelDeleter {
    void operator()(llama_model* m) const noexcept { llama_model_free(m); }
};
struct LlamaCtxDeleter {
    void operator()(llama_context* c) const noexcept { llama_free(c); }
};
struct LlamaSamplerDeleter {
    void operator()(llama_sampler* s) const noexcept { llama_sampler_free(s); }
};

using ModelPtr = std::unique_ptr<llama_model, LlamaModelDeleter>;
using ContextPtr = std::unique_ptr<llama_context, LlamaCtxDeleter>;
using SamplerPtr = std::unique_ptr<llama_sampler, LlamaSamplerDeleter>;
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
struct MtmdCtxDeleter {
    void operator()(mtmd_context* c) const noexcept { mtmd_free(c); }
};
using MtmdContextPtr = std::unique_ptr<mtmd_context, MtmdCtxDeleter>;
#endif

// llama_batch is a value type (not a pointer) allocated by llama_batch_init and
// released by llama_batch_free(llama_batch). A small move-only owning wrapper gives
// it RAII semantics without a raw owning handle.
class LlamaBatch {
public:
    LlamaBatch() = default;
    LlamaBatch(std::int32_t n_tokens, std::int32_t embd, std::int32_t n_seq_max)
        : batch_(llama_batch_init(n_tokens, embd, n_seq_max)), owned_(true) {}

    LlamaBatch(const LlamaBatch&) = delete;
    LlamaBatch& operator=(const LlamaBatch&) = delete;

    LlamaBatch(LlamaBatch&& other) noexcept
        : batch_(other.batch_), owned_(other.owned_) {
        other.owned_ = false;
    }
    LlamaBatch& operator=(LlamaBatch&& other) noexcept {
        if (this != &other) {
            reset();
            batch_ = other.batch_;
            owned_ = other.owned_;
            other.owned_ = false;
        }
        return *this;
    }

    ~LlamaBatch() { reset(); }

    [[nodiscard]] llama_batch& get() noexcept { return batch_; }
    [[nodiscard]] const llama_batch& get() const noexcept { return batch_; }

private:
    void reset() noexcept {
        if (owned_) {
            llama_batch_free(batch_);
            owned_ = false;
        }
    }

    llama_batch batch_{};
    bool owned_ = false;
};

// --- Typed decode failure (the context_overflow signaling mechanism) --------
// LlamaSession has no GenerationResult to return an error_code in, so a failing
// decode is signaled by throwing this small exception carrying a stable `code`
// string. The task-4 LlamaCppBackend catches it and copies `code` straight into
// GenerationResult::error_code (so the strings below ARE the backend's error
// vocabulary -- keep them in sync with Req 2.4 / Req 6):
//
//   "context_overflow" -- the append would push the KV position past n_ctx; no
//                          tokens were decoded (Req 2.4: typed error, never silent
//                          truncation).
//   "decode_failed"    -- llama_decode returned nonzero (Req 6 decode_failed).
//   "invalid_request"  -- tokenization itself failed (empty/degenerate input).
//
// It derives from std::runtime_error so a caller that does not special-case it
// still gets a sensible what().
struct LlamaError : std::runtime_error {
    LlamaError(std::string code_, const std::string& detail)
        : std::runtime_error(detail), code(std::move(code_)) {}
    std::string code;
};

// Process-lifetime guard: call llama_backend_init() exactly once (on first use),
// llama_backend_free() at process exit. Implemented as a function-local static so
// it is thread-safe-initialized and torn down deterministically; LlamaSession's
// constructor touches it so the backend is initialized before any model loads.
void ensure_llama_backend_initialized();

// --- LlamaSession (Req 2, 3, 5) ---------------------------------------------
// Owns the model, context, and the logical KV position. One sequence (seq_id = 0)
// is used; the R6 prefix/anchored/tail segments are just position ranges within it.
class LlamaSession {
public:
    // Loads the GGUF model and creates a context honoring n_ctx and n_gpu_layers
    // from `cfg`. Throws std::runtime_error on a load/creation failure (Req 2.2):
    // no half-initialized object is ever observable.
    LlamaSession(const std::string& model_path, const LlamaConfig& cfg);

    // Non-copyable, non-movable: it owns native handles and a logical position that
    // must not be duplicated or silently relocated.
    LlamaSession(const LlamaSession&) = delete;
    LlamaSession& operator=(const LlamaSession&) = delete;
    LlamaSession(LlamaSession&&) = delete;
    LlamaSession& operator=(LlamaSession&&) = delete;
    ~LlamaSession() = default;  // RAII members free the native handles (Req 2.3)

    // --- Tokenize / decode (task 2.2) ---------------------------------------
    // Tokenize ONE already-serialized text segment and decode it into the KV,
    // advancing the logical position. Returns the number of tokens appended.
    //
    // CHAT-TEMPLATE CONTRACT (who applies the template):
    //   decode_text decodes a *text chunk* -- it does NOT apply the model's chat
    //   template. The caller (the task-4 LlamaCppBackend) is responsible for
    //   turning a Message into role-framed text (via llama_chat_apply_template or
    //   a documented minimal framing) BEFORE calling decode_text, so the template
    //   is applied exactly once. decode_text tokenizes with parse_special=true so
    //   any control tokens the template emitted (e.g. <|im_start|>) tokenize as
    //   special tokens, and with add_special = (position()==0) so the model's BOS
    //   is added only for the very first segment and never mid-conversation.
    //
    // Throws LlamaError{"context_overflow", ...} (nothing decoded) when the append
    // would exceed n_ctx (Req 2.4); LlamaError{"decode_failed", ...} when
    // llama_decode fails; LlamaError{"invalid_request", ...} when the text does not
    // tokenize to anything.
    std::size_t decode_text(const std::string& text);

    // Evaluate a templated prompt containing `mtmd_default_marker()` placeholders alongside
    // base64-encoded or file-path images via libmtmd (handles M-RoPE 2D spatial positions).
    std::size_t decode_multimodal(const std::string& templated_text,
                                  const std::vector<std::string>& images);

    // Decode a single-token batch at the current position and return the logits
    // index to sample from (always 0 -- the one and only token in the batch has its
    // logits requested). Advances the position by 1. Used by the generate loop
    // (task 4.2). Throws LlamaError{"context_overflow"|"decode_failed", ...}.
    int decode_one(llama_token tok);

    // Capture a state snapshot at the current position on hybrid/recurrent models so
    // subsequent rollback_to(pos) restores exact GatedDeltaNet + KV states without replay.
    void capture_snapshot() const;

    // Number of tokens decoded so far == the checkpoint value. Mirrors
    // llama_memory_seq_pos_max(mem, 0) + 1 (0 for an empty sequence). pos_ is the
    // source of truth; a debug assertion checks it against the memory.
    [[nodiscard]] std::size_t position() const noexcept;

    // Remove KV entries for [pos, end) (or restore state snapshot + replay text delta
    // on hybrid/recurrent architectures) and reset the logical position to pos.
    // Throws std::out_of_range when pos > position() (Req 3.4).
    void rollback_to(std::size_t pos);

    // Cumulative count of tokens actually fed through llama_decode over this
    // session's lifetime (Req 5 prefill counter). Monotonic: never decremented by
    // rollback_to, so (post-wipe decoded) < (full-prompt decoded) is observable.
    [[nodiscard]] std::size_t prefill_tokens() const noexcept { return prefill_tokens_; }

    // Ensure the context's cached logits correspond to the token at position()-1.
    void ensure_logits_fresh();

    // --- Accessors -----------------------------------------------------------
    [[nodiscard]] const llama_model* model() const noexcept { return model_.get(); }
    [[nodiscard]] const llama_vocab* vocab() const noexcept;
    [[nodiscard]] llama_context* ctx() const noexcept { return ctx_.get(); }
    [[nodiscard]] std::size_t n_ctx() const noexcept { return n_ctx_; }
    [[nodiscard]] bool is_hybrid_or_recurrent() const noexcept { return is_hybrid_or_recurrent_; }
    [[nodiscard]] bool has_vision() const noexcept;
    [[nodiscard]] bool is_vision_loaded() const noexcept {
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
        return mtmd_ctx_ != nullptr;
#else
        return false;
#endif
    }
    [[nodiscard]] const std::string& resolved_mmproj_path() const noexcept { return mmproj_path_; }

private:
    struct SeqSnapshot {
        std::size_t pos = 0;
        std::vector<llama_token> tokens;
        std::vector<std::uint8_t> state;
    };

    void ensure_vision_loaded();

    ModelPtr model_;
    ContextPtr ctx_;
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
    MtmdContextPtr mtmd_ctx_;
#endif
    std::string mmproj_path_;
    bool mmproj_explicit_ = false;
    int vision_n_threads_ = 4;
    std::int32_t vision_n_gpu_layers_ = 0;
    bool vision_flash_attn_ = true;
    std::size_t n_ctx_ = 0;             // the context size the context was created with
    std::int32_t n_batch_ = 2048;       // batch size for mtmd/prefill helpers
    std::size_t pos_ = 0;               // mirrors the KV sequence end; the checkpoint value
    std::size_t prefill_tokens_ = 0;    // tokens actually decoded (Req 5)
    std::vector<llama_token> tokens_;   // decoded token history [0, pos_); LLAMA_TOKEN_NULL for image spans
    bool logits_fresh_ = true;          // false after rollback_to (cached logits are stale)
    bool is_hybrid_or_recurrent_ = false;
    mutable std::vector<SeqSnapshot> snapshots_;
};

#endif  // AQUILA_HAS_LLAMACPP

}  // namespace aquila


