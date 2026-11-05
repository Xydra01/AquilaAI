// LlamaSession implementation (M5 task 2.1).
//
// The ENTIRE translation unit is wrapped in `#if AQUILA_HAS_LLAMACPP` so it
// compiles to an empty object file on the stub lanes (mingw-san / msvc-asan),
// where cmake/AquilaLlamaCpp.cmake sets AQUILA_HAS_LLAMACPP=0 and never pulls in
// the llama.cpp headers or link libraries. This keeps the source list in
// src/core/CMakeLists.txt unconditional (the file is always compiled; it is just
// empty where the backend is stubbed).
//
// Scope (task 2.1): the RAII wrappers (in the header), the process-lifetime
// backend init guard, and the LlamaSession constructor (load model + create
// context honoring n_ctx / n_gpu_layers, throw a typed error on failure) plus the
// trivial accessors. decode_text / decode_one / position / rollback_to are TASK
// 2.2 -- defined here as compiling placeholders that throw so a construction test
// can run without implementing 2.2's KV logic.

#include "aquila/inference/llama_session.hpp"

#if AQUILA_HAS_LLAMACPP

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <vector>

namespace aquila {

void ensure_llama_backend_initialized() {
    // A function-local static runs its initializer exactly once (thread-safe by
    // [stmt.dcl]) and its destructor at process exit -- a zero-raw-pointer RAII
    // singleton for the llama.cpp global backend (llama_backend_init /
    // llama_backend_free). Any code path that needs llama.cpp calls this first.
    struct BackendGuard {
        BackendGuard() { llama_backend_init(); }
        ~BackendGuard() { llama_backend_free(); }
        BackendGuard(const BackendGuard&) = delete;
        BackendGuard& operator=(const BackendGuard&) = delete;
    };
    static BackendGuard guard;
    (void)guard;
}

LlamaSession::LlamaSession(const std::string& model_path, const LlamaConfig& cfg) {
    // Bring up the llama.cpp backend before touching any model (Req 2.1).
    ensure_llama_backend_initialized();

    // --- load the model, offloading n_gpu_layers per the tier (Req 2.1, R16) ---
    llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = cfg.n_gpu_layers;  // 0 for CPU tiers, 999 for gpu_high_vram

    model_.reset(llama_model_load_from_file(model_path.c_str(), mparams));
    if (model_ == nullptr) {
        // Typed failure, never a half-built object (Req 2.2). The RAII members that
        // are already constructed (none own anything yet) are cleaned up as the
        // partially-constructed object unwinds.
        throw std::runtime_error("llama: failed to load model from '" + model_path + "'");
    }

    // --- create the inference context honoring n_ctx (and n_threads) (Req 2.1, 2.4) ---
    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = cfg.n_ctx;
    if (cfg.n_threads.has_value()) {
        const auto threads = static_cast<std::int32_t>(*cfg.n_threads);
        cparams.n_threads = threads;
        cparams.n_threads_batch = threads;
    }

    ctx_.reset(llama_init_from_model(model_.get(), cparams));
    if (ctx_ == nullptr) {
        // model_ is freed by its RAII deleter as this throw unwinds the object.
        throw std::runtime_error("llama: failed to create context for model '" + model_path + "'");
    }

    // Record the ACTUAL context size the context was created with. The requested
    // n_ctx may be clamped to the model's trained size, so query it back rather
    // than trusting cfg.n_ctx (the header comment at llama_n_ctx advises this).
    n_ctx_ = static_cast<std::size_t>(llama_n_ctx(ctx_.get()));
    pos_ = 0;
    prefill_tokens_ = 0;
}

const llama_vocab* LlamaSession::vocab() const noexcept {
    return llama_model_get_vocab(model_.get());
}

namespace {

// The single sequence this session uses (R6: one logical sequence; the prefix /
// anchored / tail segments are just position ranges within it).
constexpr llama_seq_id kSeqId = 0;

// Decode a span of tokens [tokens, tokens+n) at the current end of the sequence,
// requesting logits only for the LAST token (the usual prefill convention: the
// sampler needs the logits following the final decoded token). `base_pos` is the
// position the first token in the span occupies. Returns the batch index whose
// logits were requested (the last token's slot). Throws LlamaError on failure.
//
// A llama_batch is filled by hand (rather than llama_batch_get_one, which the
// header itself flags as a transition helper to avoid) so positions, seq ids, and
// per-token logits flags are set explicitly and correctly.
int decode_span(llama_context* ctx, const llama_token* tokens, std::size_t n,
                std::size_t base_pos) {
    assert(n > 0 && "decode_span requires a non-empty span");
    const auto n_tok = static_cast<std::int32_t>(n);

    // embd = 0 (we supply token ids, not embeddings); n_seq_max = 1 (single seq).
    LlamaBatch batch(n_tok, /*embd=*/0, /*n_seq_max=*/1);
    llama_batch& b = batch.get();

    for (std::int32_t i = 0; i < n_tok; ++i) {
        b.token[i] = tokens[i];
        b.pos[i] = static_cast<llama_pos>(base_pos) + i;
        b.n_seq_id[i] = 1;
        b.seq_id[i][0] = kSeqId;
        b.logits[i] = 0;  // logits not needed for interior prefill tokens
    }
    b.n_tokens = n_tok;
    const std::int32_t last = n_tok - 1;
    b.logits[last] = 1;  // request logits for the final token only

    const std::int32_t rc = llama_decode(ctx, b);
    if (rc != 0) {
        // rc > 0 is a non-fatal warning (e.g. could not find a KV slot), rc < 0 is
        // a hard failure; either way the append did not land cleanly, so surface a
        // typed decode_failed rather than advancing the position past a bad decode.
        throw aquila::LlamaError(
            "decode_failed",
            "llama_decode returned " + std::to_string(rc) + " for a " +
                std::to_string(n_tok) + "-token batch");
    }
    return last;
}

}  // namespace

std::size_t LlamaSession::decode_text(const std::string& text) {
    const llama_vocab* v = vocab();

    // First pass: ask for the token count (a negative return is -count). BOS is
    // added only at the very start of the sequence; special/control tokens emitted
    // by an already-applied chat template are parsed, not treated as literal text.
    const bool add_special = (pos_ == 0);
    const auto text_len = static_cast<std::int32_t>(text.size());
    const std::int32_t needed = llama_tokenize(
        v, text.data(), text_len, nullptr, 0, add_special, /*parse_special=*/true);

    // needed is the (negative of the) token count; 0 means the text produced no
    // tokens (e.g. an empty string) -- nothing to decode, a degenerate request.
    const std::int32_t n_tokens = (needed < 0) ? -needed : needed;
    if (n_tokens == 0) {
        throw LlamaError("invalid_request",
                         "text tokenized to zero tokens (nothing to decode)");
    }

    std::vector<llama_token> tokens(static_cast<std::size_t>(n_tokens));
    const std::int32_t got = llama_tokenize(v, text.data(), text_len, tokens.data(),
                                            n_tokens, add_special,
                                            /*parse_special=*/true);
    if (got < 0) {
        // The buffer we just sized from the count pass should always be big enough;
        // a second negative return means the tokenizer disagrees with itself.
        throw LlamaError("invalid_request",
                         "llama_tokenize failed to fill a correctly sized buffer");
    }
    tokens.resize(static_cast<std::size_t>(got));

    // Context-overflow guard (Req 2.4): refuse the append -- decode NOTHING and
    // leave pos_ untouched -- if it would push the sequence past n_ctx. This is a
    // typed error, never a silent truncation.
    if (pos_ + tokens.size() > n_ctx_) {
        throw LlamaError(
            "context_overflow",
            "appending " + std::to_string(tokens.size()) + " tokens at position " +
                std::to_string(pos_) + " would exceed n_ctx=" +
                std::to_string(n_ctx_));
    }

    decode_span(ctx_.get(), tokens.data(), tokens.size(), pos_);

    tokens_.insert(tokens_.end(), tokens.begin(), tokens.end());  // history for reprime
    pos_ += tokens.size();
    prefill_tokens_ += tokens.size();
    logits_fresh_ = true;  // the just-decoded final token's logits are current
    return tokens.size();
}

int LlamaSession::decode_one(llama_token tok) {
    // One more token must still fit in the context window (Req 2.4).
    if (pos_ + 1 > n_ctx_) {
        throw LlamaError("context_overflow",
                         "decoding one token at position " + std::to_string(pos_) +
                             " would exceed n_ctx=" + std::to_string(n_ctx_));
    }

    const int logits_idx = decode_span(ctx_.get(), &tok, 1, pos_);
    tokens_.push_back(tok);  // history for reprime
    pos_ += 1;
    prefill_tokens_ += 1;
    logits_fresh_ = true;  // this token's logits are now current
    return logits_idx;  // always 0 for a one-token batch
}

std::size_t LlamaSession::position() const noexcept {
    // pos_ is the source of truth. In a debug build, verify it mirrors the KV
    // memory: an empty sequence reports pos_max == -1 (=> position 0); otherwise
    // position == pos_max + 1 (all positions [0, pos_max] are present).
#ifndef NDEBUG
    const llama_memory_t mem = llama_get_memory(ctx_.get());
    const llama_pos pos_max = llama_memory_seq_pos_max(mem, kSeqId);
    const auto mirrored =
        (pos_max < 0) ? std::size_t{0} : static_cast<std::size_t>(pos_max) + 1;
    assert(mirrored == pos_ && "pos_ drifted from llama_memory_seq_pos_max");
    (void)mirrored;
#endif
    return pos_;
}

void LlamaSession::rollback_to(std::size_t pos) {
    // Past-the-end rollback is the M2 interface contract violation (Req 3.4).
    if (pos > position()) {
        throw std::out_of_range(
            "LlamaSession::rollback_to: checkpoint " + std::to_string(pos) +
            " is beyond the current position " + std::to_string(position()));
    }

    const std::size_t old_end = pos_;

    // Remove KV entries for [pos, inf) -- the p1 < 0 convention -- keeping the
    // pinned prefix [0, pos) so resuming re-decodes only new tokens (Req 3.3, R6).
    const llama_memory_t mem = llama_get_memory(ctx_.get());
    llama_memory_seq_rm(mem, kSeqId, static_cast<llama_pos>(pos), -1);

    pos_ = pos;  // prefill_tokens_ is cumulative and intentionally left untouched.
    tokens_.resize(pos);  // the history now ends at the checkpoint

    // The context still holds the logits of the token that WAS last decoded (now
    // removed), so they no longer describe position pos-1. Mark them stale; the
    // next generate() calls ensure_logits_fresh() to re-prime before sampling.
    // Removing nothing (pos == old end) leaves the logits valid, so only mark stale
    // when the end actually moved.
    if (pos < old_end) {
        logits_fresh_ = false;
    }
}

void LlamaSession::ensure_logits_fresh() {
    // No-op when logits already describe position pos_-1 (no rollback since the last
    // decode), or when the sequence is empty (there is no last token to re-prime --
    // a generate from an empty context would decode something first).
    if (logits_fresh_ || pos_ == 0) {
        return;
    }

    // Re-prime: remove the single KV cell at position pos_-1 and re-decode that same
    // token there, so its logits are recomputed. Net KV state and position are
    // unchanged (we remove one cell and re-add the identical one). This is a logits
    // refresh, NOT prompt processing, so it is deliberately NOT counted toward
    // prefill_tokens_ (keeps the Req 5 post-wipe-prefill measurement clean).
    const llama_token last = tokens_.back();
    const auto last_pos = static_cast<llama_pos>(pos_ - 1);

    const llama_memory_t mem = llama_get_memory(ctx_.get());
    llama_memory_seq_rm(mem, kSeqId, last_pos, last_pos + 1);  // drop just [pos_-1, pos_)

    decode_span(ctx_.get(), &last, 1, pos_ - 1);  // re-decode it at the same position
    logits_fresh_ = true;
}

}  // namespace aquila

#endif  // AQUILA_HAS_LLAMACPP
