// LlamaCppBackend implementation (M5 task 4.1).
//
// The ENTIRE translation unit is wrapped in `#if AQUILA_HAS_LLAMACPP` so it compiles
// to an empty object file on the stub lanes (mingw-san / msvc-asan), exactly like
// llama_session.cpp and grammar.cpp. This keeps the source list in
// src/core/CMakeLists.txt unconditional; the file is always compiled, just empty
// where the backend is stubbed.
//
// Scope (task 4.1): the constructor (builds LlamaSession from LlamaConfig), append
// (role-frame a Message via the model's chat template, then decode_text),
// mark_checkpoint (position()), rollback_to (session.rollback_to), active_profile /
// supports_kv_reuse (in the header), and a COMPILING not-implemented `generate`
// stub (TODO(4.2)). The generate token loop / sampler chain / streaming / KV restore
// are task 4.2.
//
// === append() chat-template framing (the one behavior M5 must reproduce) =====
// decode_text does NOT apply the chat template (task 2.2 contract): the BACKEND
// applies it, exactly once. append() renders ONE message with its role markers via
// llama_chat_apply_template, using the model's OWN default template
// (llama_model_chat_template(model, nullptr)) so framing matches what Ollama's
// /api/chat would produce for the same model -- the parity cross-check (task 6.1)
// compares against that. add_ass is FALSE: appending a user/system/assistant/tool
// message only lays down that turn; the trailing assistant-turn opener (the "start
// of an assistant message" tokens) is added by 4.2's generate right before
// sampling, NOT on every append. This keeps the KV an exact transcript of the
// decoded turns, so mark_checkpoint / rollback positions line up with message
// boundaries and generate() can restore the KV exactly (Req 6.4).
//
// If the model carries no usable template (llama_model_chat_template returns NULL),
// we fall back to a documented minimal explicit framing in the ChatML / Qwen
// `<|im_start|>role\ncontent<|im_end|>\n` shape -- the Qwen 3.5 family (R18) uses
// ChatML, so this matches the target model when the built-in template is
// unavailable. decode_text tokenizes with parse_special=true, so those control
// tokens tokenize as the real special tokens.

#include "aquila/inference/llama_backend.hpp"

#if AQUILA_HAS_LLAMACPP

#include <chrono>
#include <cstdio>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila {

namespace {

// Render ONE message to role-framed prompt text using the model's own chat
// template (llama_model_chat_template), falling back to minimal ChatML framing when
// the model has no built-in template. add_ass is always false here (see the file
// header): the assistant-turn opener is 4.2's responsibility.
std::string frame_message(const llama_model* model, const Message& m) {
    const std::string role(to_string(m.role));

    const llama_chat_message chat{role.c_str(), m.content.c_str()};
    const char* tmpl = llama_model_chat_template(model, /*name=*/nullptr);

    if (tmpl != nullptr) {
        // First call sizes the buffer: a return > buffer length means re-alloc and
        // retry (the documented contract). Start at the header's recommended
        // 2 * total-chars estimate so the common case needs one call.
        std::vector<char> buf(2 * (role.size() + m.content.size()) + 64);
        int32_t n = llama_chat_apply_template(
            tmpl, &chat, /*n_msg=*/1, /*add_ass=*/false, buf.data(),
            static_cast<int32_t>(buf.size()));
        if (n > static_cast<int32_t>(buf.size())) {
            buf.resize(static_cast<std::size_t>(n));
            n = llama_chat_apply_template(tmpl, &chat, /*n_msg=*/1, /*add_ass=*/false,
                                          buf.data(), static_cast<int32_t>(buf.size()));
        }
        if (n > 0) {
            return std::string(buf.data(), static_cast<std::size_t>(n));
        }
        // n <= 0: the template could not be applied (unknown/unsupported template).
        // Fall through to the explicit ChatML framing below.
    }

    // Minimal explicit framing (documented fallback): ChatML / Qwen shape. Matches
    // the Qwen 3.5 family (R18) when the built-in template is unavailable.
    return "<|im_start|>" + role + "\n" + m.content + "<|im_end|>\n";
}

// Convert one sampled token to its text piece (UTF-8 bytes). llama_token_to_piece
// returns the byte count, or a NEGATIVE value (-needed) when `buf` is too small --
// the same resize contract decode_text uses for llama_tokenize. special=false so a
// control token (EOS etc.) renders as nothing user-visible; we never stream EOS
// anyway (the loop breaks on it before conversion). lstrip=0 keeps the leading
// space the tokenizer attached. A zero return means the token has no text piece
// (an empty string), which is fine -- it contributes nothing to the stream.
std::string token_to_piece(const llama_vocab* vocab, llama_token token) {
    // 64 bytes covers virtually every single token in one call; the resize path
    // below handles the rare multi-byte-run outlier.
    std::vector<char> buf(64);
    int32_t n = llama_token_to_piece(vocab, token, buf.data(),
                                     static_cast<int32_t>(buf.size()),
                                     /*lstrip=*/0, /*special=*/false);
    if (n < 0) {
        buf.resize(static_cast<std::size_t>(-n));
        n = llama_token_to_piece(vocab, token, buf.data(),
                                 static_cast<int32_t>(buf.size()),
                                 /*lstrip=*/0, /*special=*/false);
    }
    if (n <= 0) {
        return std::string{};  // no (or empty) piece for this token
    }
    return std::string(buf.data(), static_cast<std::size_t>(n));
}

// RAII scope guard that restores the KV to a captured position on destruction, so
// generate() leaves the context EXACTLY as it was on entry (Req 6.4) on EVERY exit
// path -- normal return, early error return, cancellation, or an exception thrown
// out of the token loop. rollback_to on a valid captured position cannot throw
// (checkpoint <= current end always holds here, since we only ever grow past it),
// but we still guard the destructor against any throw to keep it noexcept.
class KvRestoreGuard {
public:
    KvRestoreGuard(LlamaSession& session, std::size_t resume) noexcept
        : session_(session), resume_(resume) {}

    KvRestoreGuard(const KvRestoreGuard&) = delete;
    KvRestoreGuard& operator=(const KvRestoreGuard&) = delete;

    ~KvRestoreGuard() {
        try {
            session_.rollback_to(resume_);
        } catch (...) {
            // A destructor must not propagate. resume_ is the pre-call position, so
            // rollback_to cannot legitimately throw here; swallow defensively.
        }
    }

private:
    LlamaSession& session_;
    std::size_t resume_;
};

}  // namespace

LlamaCppBackend::LlamaCppBackend(LlamaConfig cfg)
    // LlamaSession is non-copyable / non-movable, so it is constructed directly in
    // the init list from the (as-given) config -- the caller has already derived
    // n_ctx and n_gpu_layers (0/999) from the tier (R16). Honor cfg as handed in.
    : cfg_(std::move(cfg)), session_(cfg_.model_path, cfg_) {}

void LlamaCppBackend::append(const Message& message) {
    const std::string framed = frame_message(llama_get_model(session_.ctx()), message);
    // decode_text advances the KV position; it propagates LlamaError
    // (context_overflow / decode_failed / invalid_request) on a hard failure, which
    // is acceptable for a void append (matches OllamaHttpBackend building context).
    session_.decode_text(framed);
}

std::size_t LlamaCppBackend::mark_checkpoint() const {
    return session_.position();
}

void LlamaCppBackend::rollback_to(std::size_t checkpoint) {
    // Propagates std::out_of_range when checkpoint > the current end (Req 3.4).
    session_.rollback_to(checkpoint);
}

// === build_sampler: the ordered per-call sampler chain ======================
//
// Design order (Req 4): penalties -> top_k -> top_p -> temp -> grammar -> dist,
// with greedy replacing temp+dist at temperature 0 (deterministic, Req 4.5).
//
// GenerationParams reality (checked against backend.hpp): it carries temperature,
// max_tokens, num_ctx, repeat_penalty, repeat_last_n, seed, think, keep_alive,
// constraint, timeout_s -- there are NO top_k / top_p fields. So the top_k / top_p
// links of the design order are simply absent here (there is nothing to set them
// from); the chain is penalties -> temp -> grammar -> dist (or greedy). If those
// fields are added to GenerationParams later, their links slot in between penalties
// and temp exactly where the design places them.
//
// OWNERSHIP HANDOFF (the double-free-safety crux): the chain is ONE llama_sampler*
// wrapped in a SamplerPtr. Each child created with llama_sampler_init_* is handed to
// llama_sampler_chain_add, which (per the header) "takes ownership of the sampler
// object and will free it when llama_sampler_free is called". So children are raw
// here and owned by the chain; only the chain itself is RAII-owned (SamplerPtr). The
// grammar sampler is special: GrammarFactory::make_grammar_sampler returns it already
// wrapped in a SamplerPtr. We RELEASE that SamplerPtr into the chain (chain takes
// over), so there is exactly one owner (the chain) and no double-free -- LSan on
// linux-san would catch a leak or an extra free.
SamplerPtr LlamaCppBackend::build_sampler(const GenerationParams& params,
                                          bool& grammar_null_out) {
    grammar_null_out = false;

    SamplerPtr chain(llama_sampler_chain_init(llama_sampler_chain_default_params()));
    llama_sampler* c = chain.get();

    // --- penalties (repeat only; freq/present disabled = 0.0) -------------------
    // Only add when a repeat penalty is actually requested; 1.0 is "disabled" per
    // the header, so an unset or 1.0 penalty adds no sampler. penalty_last_n defaults
    // to 64 (llama.cpp's common default) when repeat_last_n is unset.
    if (params.repeat_penalty.has_value() && *params.repeat_penalty != 1.0) {
        const int32_t n_vocab = llama_vocab_n_tokens(session_.vocab());
        const int32_t last_n =
            params.repeat_last_n.has_value()
                ? static_cast<int32_t>(*params.repeat_last_n)
                : 64;
        llama_sampler_chain_add(
            c, llama_sampler_init_penalties(
                   n_vocab, last_n,
                   static_cast<float>(*params.repeat_penalty),
                   /*penalty_freq=*/0.0F, /*penalty_present=*/0.0F));
    }

    // --- grammar (when a constraint is set) -------------------------------------
    // Resolve the GBNF for the constraint; an unparseable grammar yields a null
    // SamplerPtr, which we report via grammar_null_out so generate() returns
    // invalid_request WITHOUT running the loop (Req 4.3). The grammar is added
    // AFTER temp and BEFORE dist per the design order, so we stage it and add it in
    // the right place below.
    SamplerPtr grammar;  // held until we release it into the chain
    if (params.constraint.kind != OutputConstraint::Kind::none) {
        const std::optional<std::string> gbnf = grammar_.gbnf_for(params.constraint);
        if (gbnf.has_value()) {
            grammar = grammar_.make_grammar_sampler(session_.vocab(), *gbnf);
            if (grammar == nullptr) {
                grammar_null_out = true;
                return SamplerPtr{};  // caller maps to invalid_request
            }
        }
        // gbnf == nullopt only for Kind::none, already excluded; defensively, a
        // missing gbnf for a set constraint leaves the model unconstrained.
    }

    if (params.temperature == 0.0) {
        // Deterministic greedy: no temp, no dist -- argmax selection (Req 4.5).
        // Grammar (if any) still applies before the greedy pick so the output stays
        // schema-valid.
        if (grammar != nullptr) {
            llama_sampler_chain_add(c, grammar.release());  // chain now owns it
        }
        llama_sampler_chain_add(c, llama_sampler_init_greedy());
    } else {
        // Stochastic: temp -> grammar -> dist(seed). A fixed seed makes this
        // reproducible (Req 4.5); an unset seed uses LLAMA_DEFAULT_SEED (random).
        llama_sampler_chain_add(c, llama_sampler_init_temp(
                                       static_cast<float>(params.temperature)));
        if (grammar != nullptr) {
            llama_sampler_chain_add(c, grammar.release());  // chain now owns it
        }
        const uint32_t seed =
            params.seed.has_value()
                ? static_cast<uint32_t>(static_cast<uint64_t>(*params.seed))
                : LLAMA_DEFAULT_SEED;
        llama_sampler_chain_add(c, llama_sampler_init_dist(seed));
    }

    return chain;
}

GenerationResult LlamaCppBackend::generate(const GenerationParams& params,
                                           const TokenCallback& on_token) {
    using clock = std::chrono::steady_clock;

    // Step 1: capture the pre-call position. The KV is restored to exactly this on
    // every exit path by the scope guard below (Req 6.4), so generate() leaves the
    // context unchanged and the caller appends the reply itself to keep it.
    const std::size_t resume = session_.position();
    KvRestoreGuard restore(session_, resume);

    // After a rollback_to (a context wipe, R6), the context's cached logits belong
    // to a now-removed token, so sampling from idx=-1 would read stale logits. Re-
    // prime the logits at the resume position before the first sample so generate()
    // samples from the RIGHT position (fixes the Property 1 "rollback is exact"
    // finding). A no-op when logits are already fresh (no rollback since the last
    // decode) or the context is empty.
    session_.ensure_logits_fresh();

    // Step 2: build the sampler chain. A set-but-unparseable grammar short-circuits
    // to invalid_request without decoding anything (the guard still restores the KV,
    // which is a no-op here since nothing was decoded).
    std::fprintf(stderr, "[trace] before build_sampler\n"); std::fflush(stderr);
    bool grammar_null = false;
    SamplerPtr sampler = build_sampler(params, grammar_null);
    std::fprintf(stderr, "[trace] after build_sampler (null=%d)\n", int(grammar_null)); std::fflush(stderr);
    if (grammar_null) {
        return GenerationResult{
            /*ok=*/false,
            /*error_code=*/"invalid_request",
            /*error_detail=*/"grammar could not be parsed from the output constraint",
        };
    }

    const llama_vocab* vocab = session_.vocab();
    llama_context* ctx = session_.ctx();

    GenerationResult result;
    std::string content;

    // The first sample reads the logits of the LAST already-decoded token. The
    // previous append (decode_text/decode_span) requested logits for its final
    // token, so idx == -1 ("the last token in the batch", per the header's sample
    // usage) samples from the right position. After each decode_one, its one-token
    // batch again leaves the sampling logits at -1, so -1 holds for the whole loop.
    constexpr int32_t kLastLogits = -1;

    // max_tokens == unset means "no explicit cap"; the context window (n_ctx) is the
    // real bound and decode_one raises context_overflow if we hit it.
    const bool capped = params.max_tokens.has_value();
    const std::uint64_t max_tokens =
        capped ? static_cast<std::uint64_t>(*params.max_tokens) : 0;

    std::uint64_t completion_tokens = 0;
    auto last_progress = clock::now();
    std::fprintf(stderr, "[trace] entering token loop\n"); std::fflush(stderr);

    for (;;) {
        // No-progress timeout (Req 6.3): if too long elapses without completing a
        // token, stop with stream_stalled. Checked at the top of each iteration
        // against wall-clock since the last token was produced.
        const double since =
            std::chrono::duration<double>(clock::now() - last_progress).count();
        if (since > params.timeout_s) {
            result.ok = false;
            result.error_code = "stream_stalled";
            result.error_detail = "no token produced within timeout_s";
            break;
        }

        // Sample the next token from the last token's logits. llama_sampler_sample
        // applies the chain AND accepts the token internally (so the grammar sampler
        // advances its state on the accepted token -- no explicit accept needed).
        if (completion_tokens == 0) { std::fprintf(stderr, "[trace] before first sample\n"); std::fflush(stderr); }
        const llama_token tok = llama_sampler_sample(sampler.get(), ctx, kLastLogits);
        if (completion_tokens == 0) { std::fprintf(stderr, "[trace] after first sample tok=%d\n", int(tok)); std::fflush(stderr); }

        // EOS (end of generation): natural stop, BEFORE converting to text (we never
        // stream the EOS piece) and BEFORE decoding it into the KV.
        if (llama_vocab_is_eog(vocab, tok)) {
            result.ok = true;
            result.done_reason = "stop";
            break;
        }

        // Decode the sampled token to advance the KV and produce the next logits.
        // A hard decode failure surfaces as a typed LlamaError; map .code straight
        // into the error vocabulary (context_overflow / decode_failed / ...).
        try {
            session_.decode_one(tok);
        } catch (const LlamaError& e) {
            result.ok = false;
            result.error_code = e.code;  // context_overflow | decode_failed | ...
            result.error_detail = e.what();
            break;
        }

        ++completion_tokens;

        // Convert and stream. An empty piece still counts as a produced token (it
        // advances the loop and resets the stall timer) but streams nothing.
        const std::string piece = token_to_piece(vocab, tok);
        if (!piece.empty()) {
            content += piece;
        }
        last_progress = clock::now();

        if (on_token) {
            // thinking is not separated at this layer (no reasoning-channel parsing
            // in M5); pass empty thinking. A false return is an explicit cancel.
            const bool keep_going = on_token(piece, std::string_view{});
            if (!keep_going) {
                result.ok = false;
                result.error_code = "cancelled";
                result.error_detail = "generation cancelled by callback";
                break;
            }
        }

        // max_tokens reached: stop with done_reason="length" (Req 6.2).
        if (capped && completion_tokens >= max_tokens) {
            result.ok = true;
            result.done_reason = "length";
            break;
        }
    }

    // Step 4: fill the result. prompt_tokens is the context the reply was generated
    // from (the resume position); completion_tokens is how many tokens we generated
    // (regardless of stop cause). content holds the accumulated reply.
    result.content = std::move(content);
    result.prompt_tokens = static_cast<std::uint64_t>(resume);
    result.completion_tokens = completion_tokens;

    // Step 5: the KvRestoreGuard destructor rolls the KV back to `resume` here, so
    // the context is exactly as before the call (Req 6.4).
    return result;
}

}  // namespace aquila

#endif  // AQUILA_HAS_LLAMACPP
