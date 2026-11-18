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

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila {

namespace {

common_chat_msg make_text_chat_msg(std::string role, std::string content) {
    common_chat_msg msg;
    msg.role = std::move(role);
    msg.content = std::move(content);
    return msg;
}

std::string default_media_marker() {
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
    return mtmd_default_marker();
#else
    return "<__media__>";
#endif
}

std::string render_content_with_markers(const std::string& content, std::size_t n_images) {
    if (n_images == 0) {
        return content;
    }
    std::string out;
    const std::string marker = default_media_marker();
    for (std::size_t i = 0; i < n_images; ++i) {
        out += marker;
    }
    if (!content.empty()) {
        out += '\n';
        out += content;
    }
    return out;
}

std::size_t count_occurrences(std::string_view haystack, std::string_view needle) {
    if (needle.empty()) {
        return 0;
    }
    std::size_t count = 0;
    std::size_t pos = 0;
    while ((pos = haystack.find(needle, pos)) != std::string_view::npos) {
        ++count;
        pos += needle.size();
    }
    return count;
}

common_chat_msg to_chat_msg(const std::string& role,
                            const std::string& content,
                            std::size_t n_images) {
    common_chat_msg cmsg;
    cmsg.role = role;
    if (n_images == 0) {
        cmsg.content = content;
    } else {
        const std::string marker = default_media_marker();
        for (std::size_t i = 0; i < n_images; ++i) {
            cmsg.content_parts.push_back(
                common_chat_msg_content_part{"media_marker", marker, {}});
        }
        if (!content.empty()) {
            cmsg.content_parts.push_back(
                common_chat_msg_content_part{"text", "\n" + content, {}});
        }
    }
    return cmsg;
}

// Render ONE message via the model's full Jinja template (`common_chat_templates`)
// using a constant minimal dummy anchor when pos > 0 so past history offsets never
// mutate AND non-leading Role::system messages are re-homed to Role::user (Qwen 3.5's
// Jinja silently ignores any system message after the leading system turn).
std::string frame_message(const common_chat_templates* tmpls,
                          const Message& m,
                          bool is_first) {
    std::string effective_role;
    std::string effective_content;
    if (!is_first && m.role == Role::system) {
        effective_role = "user";
        effective_content = "[Context State]\n" + m.content;
    } else {
        effective_role = std::string(to_string(m.role));
        effective_content = m.content;
    }

    const common_chat_msg cmsg = to_chat_msg(effective_role, effective_content, m.images.size());

    std::string framed;
    if (tmpls != nullptr) {
        try {
            auto apply_msgs = [&](std::vector<common_chat_msg> msgs) {
                common_chat_templates_inputs in;
                in.messages = std::move(msgs);
                in.add_generation_prompt = false;
                in.use_jinja = true;
                in.reasoning_format = COMMON_REASONING_FORMAT_NONE;
                in.enable_thinking = false;
                in.force_pure_content = true;
                return common_chat_templates_apply(tmpls, in).prompt.str();
            };

            if (is_first && effective_role != "tool") {
                framed = apply_msgs({cmsg});
            } else {
                std::vector<common_chat_msg> anchor;
                anchor.push_back(make_text_chat_msg("system", "sys"));
                anchor.push_back(make_text_chat_msg("user", "usr"));
                if (effective_role == "tool") {
                    anchor.push_back(make_text_chat_msg("assistant", "ok"));
                }
                const std::string base = apply_msgs(anchor);
                anchor.push_back(cmsg);
                const std::string full = apply_msgs(std::move(anchor));
                if (full.size() > base.size() && full.compare(0, base.size(), base) == 0) {
                    framed = full.substr(base.size());
                }
            }
        } catch (...) {
            framed.clear();
        }
    }

    if (framed.empty()) {
        framed = "<|im_start|>" + effective_role + "\n" +
                 render_content_with_markers(effective_content, m.images.size()) +
                 "<|im_end|>\n";
    }

    // Some Jinja templates (including Qwen 3.5's) can drop `media_marker` parts inside
    // non-user roles such as `tool`. If any attached image would lose its `<__media__>`
    // marker, fall back to a user-framed visual observation block so `mtmd_tokenize`
    // always receives the exact number of markers matching `m.images`.
    if (!m.images.empty()) {
        const std::string marker = default_media_marker();
        if (count_occurrences(framed, marker) < m.images.size()) {
            const std::string obs_text = effective_role == "tool"
                ? "[Visual Tool Observation]\n" + effective_content
                : effective_content;
            std::string fallback_framed;
            if (tmpls != nullptr) {
                try {
                    const common_chat_msg obs_msg = to_chat_msg("user", obs_text, m.images.size());
                    std::vector<common_chat_msg> anchor;
                    if (!is_first) {
                        anchor.push_back(make_text_chat_msg("system", "sys"));
                        anchor.push_back(make_text_chat_msg("user", "usr"));
                    }
                    auto apply_obs = [&](std::vector<common_chat_msg> msgs) {
                        common_chat_templates_inputs in;
                        in.messages = std::move(msgs);
                        in.add_generation_prompt = false;
                        in.use_jinja = true;
                        in.reasoning_format = COMMON_REASONING_FORMAT_NONE;
                        in.enable_thinking = false;
                        in.force_pure_content = true;
                        return common_chat_templates_apply(tmpls, in).prompt.str();
                    };
                    if (is_first) {
                        fallback_framed = apply_obs({obs_msg});
                    } else {
                        const std::string base = apply_obs(anchor);
                        anchor.push_back(obs_msg);
                        const std::string full = apply_obs(std::move(anchor));
                        if (full.size() > base.size() && full.compare(0, base.size(), base) == 0) {
                            fallback_framed = full.substr(base.size());
                        }
                    }
                } catch (...) {
                    fallback_framed.clear();
                }
            }
            if (count_occurrences(fallback_framed, marker) >= m.images.size()) {
                framed = std::move(fallback_framed);
            } else {
                framed = "<|im_start|>user\n" +
                         render_content_with_markers(obs_text, m.images.size()) +
                         "<|im_end|>\n";
            }
        }
    }

    if (!is_first) {
        constexpr std::string_view kBosToken = "<|begin_of_text|>";
        if (framed.rfind(kBosToken, 0) == 0) {
            framed = framed.substr(kBosToken.size());
            if (!framed.empty() && framed.front() == '\n') {
                framed.erase(0, 1);
            }
        }
    }

    return framed;
}

std::string build_generation_opener(const common_chat_templates* tmpls, bool enable_thinking) {
    if (tmpls != nullptr) {
        try {
            std::vector<common_chat_msg> msgs;
            msgs.push_back(make_text_chat_msg("system", "sys"));
            msgs.push_back(make_text_chat_msg("user", "usr"));

            common_chat_templates_inputs in;
            in.messages = std::move(msgs);
            in.use_jinja = true;
            in.reasoning_format = COMMON_REASONING_FORMAT_NONE;
            in.enable_thinking = enable_thinking;
            in.force_pure_content = true;

            in.add_generation_prompt = false;
            const std::string without_prompt = common_chat_templates_apply(tmpls, in).prompt.str();

            in.add_generation_prompt = true;
            const auto with_res = common_chat_templates_apply(tmpls, in);
            const std::string with_prompt = with_res.prompt.str();

            if (with_prompt.size() > without_prompt.size() &&
                with_prompt.compare(0, without_prompt.size(), without_prompt) == 0) {
                return with_prompt.substr(without_prompt.size());
            }
            if (!with_res.generation_prompt.empty()) {
                return with_res.generation_prompt;
            }
        } catch (...) {
            // Fall through to deterministic ChatML opener.
        }
    }
    return enable_thinking
        ? std::string{"<|im_start|>assistant\n"}
        : std::string{"<|im_start|>assistant\n<think>\n\n</think>\n\n"};
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
// Fill reusable candidate buffer from context logits and pick a token via `chain`.
llama_token sample_chain_from_logits(const float* logits,
                                     int n_vocab,
                                     llama_sampler* chain,
                                     llama_sampler* pre_grammar,
                                     std::vector<llama_token_data>& cur) {
    cur.resize(static_cast<std::size_t>(n_vocab));
    for (llama_token id = 0; id < n_vocab; ++id) {
        cur[static_cast<std::size_t>(id)] = llama_token_data{id, logits[id], 0.0f};
    }
    llama_token_data_array cur_p{cur.data(), cur.size(), -1, false};
    if (pre_grammar != nullptr) {
        llama_sampler_apply(pre_grammar, &cur_p);
    }
    llama_sampler_apply(chain, &cur_p);
    if (cur_p.selected < 0 || static_cast<std::size_t>(cur_p.selected) >= cur_p.size) {
        return LLAMA_TOKEN_NULL;
    }
    return cur_p.data[cur_p.selected].id;
}

// Grammar-based rejection sampling (matches llama.cpp common_sampler_sample):
// sample from `chain` first (<1 ms), probe that single token against `grammar`,
// and only evaluate `grammar` across all vocab logits if rejected.
llama_token sample_next_token(llama_context* ctx,
                              const llama_vocab* vocab,
                              int32_t idx,
                              llama_sampler* chain,
                              llama_sampler* grammar,
                              std::vector<llama_token_data>& cur) {
    if (grammar == nullptr) {
        return llama_sampler_sample(chain, ctx, idx);
    }
    const int n_vocab = llama_vocab_n_tokens(vocab);
    const float* logits = llama_get_logits_ith(ctx, idx);
    if (n_vocab <= 0 || logits == nullptr) {
        return LLAMA_TOKEN_NULL;
    }

    llama_token tok = sample_chain_from_logits(logits, n_vocab, chain, nullptr, cur);
    if (tok == LLAMA_TOKEN_NULL) {
        return LLAMA_TOKEN_NULL;
    }

    llama_token_data probe{tok, 1.0f, 0.0f};
    llama_token_data_array probe_arr{&probe, 1, -1, false};
    llama_sampler_apply(grammar, &probe_arr);
    if (!std::isfinite(probe.logit)) {
        tok = sample_chain_from_logits(logits, n_vocab, chain, grammar, cur);
        if (tok == LLAMA_TOKEN_NULL) {
            return LLAMA_TOKEN_NULL;
        }
    }

    llama_sampler_accept(grammar, tok);
    llama_sampler_accept(chain, tok);
    return tok;
}

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
    : cfg_(std::move(cfg)),
      session_(cfg_.model_path, cfg_),
      tmpls_(common_chat_templates_init(session_.model(), "")) {}

void LlamaCppBackend::append(const Message& message) {
    const bool is_first = (session_.position() == 0);
    const std::string framed = frame_message(tmpls_.get(), message, is_first);
    if (message.images.empty()) {
        session_.decode_text(framed);
    } else {
        session_.decode_multimodal(framed, message.images);
    }
}

std::size_t LlamaCppBackend::mark_checkpoint() const {
    session_.capture_snapshot();
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
                                          bool& grammar_null_out,
                                          SamplerPtr& grammar_out) {
    grammar_null_out = false;
    grammar_out.reset();

    SamplerPtr chain(llama_sampler_chain_init(llama_sampler_chain_default_params()));
    llama_sampler* c = chain.get();

    // --- penalties (repeat + presence) -----------------------------------------
    const double repeat_pen = params.repeat_penalty.value_or(1.0);
    const double presence_pen = params.presence_penalty.value_or(0.0);
    if (repeat_pen != 1.0 || presence_pen != 0.0) {
        const int32_t n_vocab = llama_vocab_n_tokens(session_.vocab());
        const int32_t last_n =
            params.repeat_last_n.has_value()
                ? static_cast<int32_t>(*params.repeat_last_n)
                : 64;
        llama_sampler_chain_add(
            c, llama_sampler_init_penalties(
                   n_vocab, last_n,
                   static_cast<float>(repeat_pen),
                   /*penalty_freq=*/0.0F,
                   static_cast<float>(presence_pen)));
    }

    // --- grammar (validated up front, applied via rejection sampling) ----------
    if (params.constraint.kind != OutputConstraint::Kind::none) {
        const std::optional<std::string> gbnf = grammar_.gbnf_for(params.constraint);
        if (gbnf.has_value()) {
            grammar_out = grammar_.make_grammar_sampler(session_.vocab(), *gbnf);
            if (grammar_out == nullptr) {
                grammar_null_out = true;
                return SamplerPtr{};
            }
        }
    }

    if (params.temperature == 0.0) {
        llama_sampler_chain_add(c, llama_sampler_init_greedy());
    } else {
        if (params.top_k.has_value() && *params.top_k > 0) {
            llama_sampler_chain_add(c, llama_sampler_init_top_k(static_cast<int32_t>(*params.top_k)));
        }
        if (params.top_p.has_value() && *params.top_p < 1.0) {
            llama_sampler_chain_add(
                c, llama_sampler_init_top_p(static_cast<float>(*params.top_p), /*min_keep=*/1));
        }
        if (params.min_p.has_value() && *params.min_p > 0.0) {
            llama_sampler_chain_add(
                c, llama_sampler_init_min_p(static_cast<float>(*params.min_p), /*min_keep=*/1));
        }
        llama_sampler_chain_add(c, llama_sampler_init_temp(
                                       static_cast<float>(params.temperature)));
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

    const std::size_t resume = session_.position();
    KvRestoreGuard restore(session_, resume);

    // Constrained JSON passes disable native <think> emission unless explicitly requested;
    // open chat/analysis allows native <think> by default.
    const bool enable_thinking =
        params.think.value_or(params.constraint.kind == OutputConstraint::Kind::none);
    const std::string opener = build_generation_opener(tmpls_.get(), enable_thinking);
    const bool start_in_think = opener_starts_in_think(opener);

    if (!opener.empty()) {
        try {
            session_.decode_text(opener);
        } catch (const LlamaError&) {
            // Opener undecodable: fall through; the loop still runs from current logits.
        }
    }

    session_.ensure_logits_fresh();

    bool grammar_null = false;
    SamplerPtr grammar_sampler;
    SamplerPtr sampler = build_sampler(params, grammar_null, grammar_sampler);
    if (grammar_null) {
        GenerationResult gr;
        gr.ok = false;
        gr.error_code = "invalid_request";
        gr.error_detail = "grammar could not be parsed from the output constraint";
        return gr;
    }

    const llama_vocab* vocab = session_.vocab();
    llama_context* ctx = session_.ctx();

    GenerationResult result;
    std::string content;
    std::string thinking;
    ThinkStreamSplitter splitter(start_in_think);
    std::vector<llama_token_data> cur_candidates;

    constexpr int32_t kLastLogits = -1;

    const bool capped = params.max_tokens.has_value();
    const std::uint64_t max_tokens =
        capped ? static_cast<std::uint64_t>(*params.max_tokens) : 0;

    std::uint64_t completion_tokens = 0;
    std::uint64_t empty_piece_run = 0;
    auto last_progress = clock::now();

    for (;;) {
        const double since =
            std::chrono::duration<double>(clock::now() - last_progress).count();
        if (since > params.timeout_s) {
            result.ok = false;
            result.error_code = "stream_stalled";
            result.error_detail = "no token produced within timeout_s";
            break;
        }

        const llama_token tok = sample_next_token(
            ctx, vocab, kLastLogits, sampler.get(), grammar_sampler.get(), cur_candidates);
        if (tok == LLAMA_TOKEN_NULL) {
            result.ok = false;
            result.error_code = "decode_failed";
            result.error_detail = "sampler failed to select a valid token";
            break;
        }

        if (llama_vocab_is_eog(vocab, tok)) {
            result.ok = true;
            result.done_reason = "stop";
            break;
        }

        try {
            session_.decode_one(tok);
        } catch (const LlamaError& e) {
            result.ok = false;
            result.error_code = e.code;
            result.error_detail = e.what();
            break;
        }

        ++completion_tokens;

        const std::string raw_piece = token_to_piece(vocab, tok);
        if (raw_piece.empty()) {
            if (++empty_piece_run >= 16) {
                result.ok = false;
                result.error_code = "degenerate_output";
                result.error_detail = "model emitted a run of zero-width tokens (stuck)";
                break;
            }
        } else {
            empty_piece_run = 0;
        }

        std::string piece_content;
        std::string piece_thinking;
        splitter.push(raw_piece, piece_content, piece_thinking);
        const bool hit_cap = (capped && completion_tokens >= max_tokens);
        if (hit_cap) {
            splitter.flush(piece_content, piece_thinking);
        }

        if (!piece_content.empty()) {
            content += piece_content;
        }
        if (!piece_thinking.empty()) {
            thinking += piece_thinking;
        }
        last_progress = clock::now();

        if (on_token) {
            const bool keep_going = on_token(piece_content, piece_thinking);
            if (!keep_going) {
                result.ok = false;
                result.error_code = "cancelled";
                result.error_detail = "generation cancelled by callback";
                break;
            }
        }

        if (hit_cap) {
            result.ok = true;
            result.done_reason = "length";
            break;
        }
    }

    result.content = std::move(content);
    result.thinking = std::move(thinking);
    result.prompt_tokens = static_cast<std::uint64_t>(resume);
    result.completion_tokens = completion_tokens;

    return result;
}

}  // namespace aquila

#endif  // AQUILA_HAS_LLAMACPP
