// LlamaSession implementation (M5 task 2.1).
//
// The ENTIRE translation unit is wrapped in `#if AQUILA_HAS_LLAMACPP` so it
// compiles to an empty object file on the stub lanes (mingw-san / msvc-asan),
// where cmake/AquilaLlamaCpp.cmake sets AQUILA_HAS_LLAMACPP=0 and never pulls
// in the llama.cpp headers or link libraries. This keeps the source list in
// src/core/CMakeLists.txt unconditional (the file is always compiled; it is
// just empty where the backend is stubbed).
//
// Scope (task 2.1): the RAII wrappers (in the header), the process-lifetime
// backend init guard, and the LlamaSession constructor (load model + create
// context honoring n_ctx / n_gpu_layers, throw a typed error on failure) plus
// the trivial accessors. decode_text / decode_one / position / rollback_to are
// TASK 2.2 -- defined here as compiling placeholders that throw so a
// construction test can run without implementing 2.2's KV logic.

#include "aquila/inference/llama_session.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace aquila {

namespace {

std::string to_lower_copy(std::string_view s) {
  std::string out(s);
  for (char &ch : out) {
    ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
  }
  return out;
}

std::string extract_size_tag(std::string_view lower_name) {
  // Ordered longest-first so "27b"/"35b" do not partially match shorter tags.
  constexpr std::array<std::string_view, 11> kTags = {
      "122b", "35b", "32b", "27b", "14b", "9b", "8b", "7b", "4b", "3b", "2b"};
  for (std::string_view tag : kTags) {
    const std::size_t pos = lower_name.find(tag);
    if (pos == std::string_view::npos)
      continue;
    const bool left_ok =
        (pos == 0) ||
        !std::isdigit(static_cast<unsigned char>(lower_name[pos - 1]));
    const std::size_t end = pos + tag.size();
    const bool right_ok =
        (end == lower_name.size()) ||
        !std::isalnum(static_cast<unsigned char>(lower_name[end]));
    if (left_ok && right_ok) {
      return std::string(tag);
    }
  }
  return {};
}

int score_mmproj_candidate(const std::filesystem::path &cand,
                           const std::string &model_tag,
                           const std::filesystem::path &model_dir) {
  const std::string fname = to_lower_copy(cand.filename().string());
  if (fname.rfind("mmproj", 0) != 0 || cand.extension() != ".gguf") {
    return -1;
  }
  const std::string cand_tag = extract_size_tag(fname);
  const std::string dir_tag =
      extract_size_tag(to_lower_copy(cand.parent_path().filename().string()));
  const std::string effective_tag = !cand_tag.empty() ? cand_tag : dir_tag;

  if (!model_tag.empty() && !effective_tag.empty() &&
      effective_tag != model_tag) {
    return -1; // Dimension mismatch (e.g. never load 9B mmproj on 4B)
  }

  int score = 10;
  if (!model_tag.empty() && effective_tag == model_tag) {
    score += 100;
  }
  if (cand.parent_path() == model_dir) {
    score += 50;
  }
  if (fname.find("bf16") != std::string::npos ||
      fname.find("f16") != std::string::npos) {
    score += 20;
  }
  return score;
}

} // namespace

std::string discover_mmproj_for_model(const std::string &model_path) {
  if (model_path.empty())
    return {};
  std::error_code ec;
  const std::filesystem::path mp(model_path);
  const std::filesystem::path model_dir = mp.parent_path();
  const std::string model_tag =
      extract_size_tag(to_lower_copy(mp.filename().string()));
  const std::string lower_model = to_lower_copy(mp.filename().string());

  std::filesystem::path best;
  int best_score = -1;

  auto consider = [&](const std::filesystem::path &p) {
    if (!std::filesystem::is_regular_file(p, ec))
      return;
    const int s = score_mmproj_candidate(p, model_tag, model_dir);
    if (s > best_score) {
      best_score = s;
      best = p;
    }
  };

  if (!model_dir.empty() && std::filesystem::is_directory(model_dir, ec)) {
    for (const auto &entry :
         std::filesystem::directory_iterator(model_dir, ec)) {
      consider(entry.path());
    }
  }

  // Known local repositories for Qwen 3.5 when GGUF lives outside the LM Studio
  // folder.
  if (best.empty() && lower_model.find("qwen") != std::string::npos) {
    if (model_tag == "4b") {
      consider("F:/aquila-models/mmproj-Qwen3.5-4B-F16.gguf");
      consider("F:/Users/myfri/agent-projects/mmproj-Qwen3.5-4B-F16.gguf");
      consider("F:/Users/myfri/agent-projects/mmproj-Qwen3.5-4B-BF16.gguf");
    } else if (model_tag == "9b") {
      consider("F:/aquila-models/mmproj-Qwen3.5-9B-BF16.gguf");
      consider("F:/Users/myfri/.lmstudio/models/lmstudio-community/"
               "Qwen3.5-9B-GGUF/mmproj-Qwen3.5-9B-BF16.gguf");
      consider("F:/Users/myfri/agent-projects/mmproj-Qwen3.5-9B-BF16.gguf");
      consider("F:/Users/myfri/agent-projects/mmproj-Qwen3.5-9B-F16.gguf");
    }
  }

  return best.empty() ? std::string{} : best.generic_string();
}

} // namespace aquila

#if AQUILA_HAS_LLAMACPP

namespace aquila {

void ensure_llama_backend_initialized() {
  // A function-local static runs its initializer exactly once (thread-safe by
  // [stmt.dcl]) and its destructor at process exit -- a zero-raw-pointer RAII
  // singleton for the llama.cpp global backend (llama_backend_init /
  // llama_backend_free). Any code path that needs llama.cpp calls this first.
  struct BackendGuard {
    BackendGuard() { llama_backend_init(); }
    ~BackendGuard() { llama_backend_free(); }
    BackendGuard(const BackendGuard &) = delete;
    BackendGuard &operator=(const BackendGuard &) = delete;
  };
  static BackendGuard guard;
  (void)guard;
}

LlamaSession::LlamaSession(const std::string &model_path,
                           const LlamaConfig &cfg) {
  // Bring up the llama.cpp backend before touching any model (Req 2.1).
  ensure_llama_backend_initialized();

  // --- load the model, offloading n_gpu_layers per the tier (Req 2.1, R16) ---
  llama_model_params mparams = llama_model_default_params();
  mparams.n_gpu_layers =
      cfg.n_gpu_layers; // 0 for CPU tiers, 999 for gpu_high_vram
  std::array<ggml_backend_dev_t, 2> cpu_only_devs{};
  if (cfg.n_gpu_layers == 0) {
    if (ggml_backend_dev_t cpu_dev =
            ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_CPU)) {
      cpu_only_devs = {cpu_dev, nullptr};
      mparams.devices = cpu_only_devs.data();
    }
  }

  model_.reset(llama_model_load_from_file(model_path.c_str(), mparams));
  if (model_ == nullptr) {
    throw std::runtime_error("llama: failed to load model from '" + model_path +
                             "'");
  }

  is_hybrid_or_recurrent_ = llama_model_is_hybrid(model_.get()) ||
                            llama_model_is_recurrent(model_.get());

  // --- create the inference context honoring n_ctx, FA, and KV quantization
  // ---
  auto make_cparams = [&](ggml_type tk, ggml_type tv) {
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = cfg.n_ctx;
    cp.n_batch = std::min<std::uint32_t>(cfg.n_ctx, 2048);
    cp.n_ubatch = 512;
    if (cfg.n_gpu_layers == 0) {
      cp.offload_kqv = false;
      cp.op_offload = false;
      cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED;
    } else {
      cp.flash_attn_type = cfg.flash_attn
                               ? LLAMA_FLASH_ATTN_TYPE_ENABLED
                               : LLAMA_FLASH_ATTN_TYPE_AUTO;
    }
    cp.type_k = tk;
    cp.type_v = tv;
    if (cfg.n_threads.has_value()) {
      const auto threads = static_cast<std::int32_t>(*cfg.n_threads);
      cp.n_threads = threads;
      cp.n_threads_batch = threads;
    }
    return cp;
  };

  const bool use_gpu_kv_q8 =
      (cfg.n_gpu_layers != 0 && cfg.flash_attn && cfg.kv_quant_q8);
  if (use_gpu_kv_q8) {
    ctx_.reset(llama_init_from_model(
        model_.get(), make_cparams(GGML_TYPE_Q8_0, GGML_TYPE_Q8_0)));
    if (ctx_ == nullptr) {
      // Fallback: Q8_0 K + F16 V if V-quant kernel is unsupported for
      // head_dim=256
      ctx_.reset(llama_init_from_model(
          model_.get(), make_cparams(GGML_TYPE_Q8_0, GGML_TYPE_F16)));
    }
  }
  if (ctx_ == nullptr) {
    ctx_.reset(llama_init_from_model(
        model_.get(), make_cparams(GGML_TYPE_F16, GGML_TYPE_F16)));
  }
  if (ctx_ == nullptr) {
    throw std::runtime_error("llama: failed to create context for model '" +
                             model_path + "'");
  }

#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
  vision_n_threads_ =
      cfg.n_threads.has_value() ? static_cast<int>(*cfg.n_threads) : 4;
  vision_n_gpu_layers_ = cfg.n_gpu_layers;
  vision_flash_attn_ = cfg.flash_attn;
  mmproj_explicit_ = !cfg.mmproj_path.empty();

  std::string resolved_mm = cfg.mmproj_path;
  if (resolved_mm.empty() && cfg.auto_discover_mmproj) {
    resolved_mm = discover_mmproj_for_model(model_path);
  }
  if (!resolved_mm.empty()) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(resolved_mm, ec)) {
      if (mmproj_explicit_) {
        throw std::runtime_error(
            "llama: configured mmproj file does not exist: '" + resolved_mm +
            "'");
      }
      resolved_mm.clear();
    }
  }
  mmproj_path_ = resolved_mm;
  if (!mmproj_path_.empty() && cfg.eager_load_mmproj) {
    ensure_vision_loaded();
  }
#endif

  // Record the ACTUAL context size the context was created with.
  n_ctx_ = static_cast<std::size_t>(llama_n_ctx(ctx_.get()));
  n_batch_ = static_cast<std::int32_t>(llama_n_batch(ctx_.get()));
  pos_ = 0;
  prefill_tokens_ = 0;
}

const llama_vocab *LlamaSession::vocab() const noexcept {
  return llama_model_get_vocab(model_.get());
}

void LlamaSession::ensure_vision_loaded() {
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
  if (mtmd_ctx_ != nullptr || mmproj_path_.empty()) {
    return;
  }
  mtmd_context_params mp = mtmd_context_params_default();
  mp.use_gpu = (vision_n_gpu_layers_ != 0);
  mp.n_threads = vision_n_threads_;
  mp.flash_attn_type = (vision_n_gpu_layers_ != 0 && vision_flash_attn_)
                           ? LLAMA_FLASH_ATTN_TYPE_ENABLED
                           : LLAMA_FLASH_ATTN_TYPE_AUTO;
  mp.print_timings = false;
  mtmd_ctx_.reset(mtmd_init_from_file(mmproj_path_.c_str(), model_.get(), mp));
  if (mtmd_ctx_ == nullptr) {
    if (mmproj_explicit_) {
      throw LlamaError("invalid_request",
                       "llama: failed to initialize mtmd vision context from '" +
                           mmproj_path_ + "'");
    }
    // Auto-discovered candidate failed (e.g. dimension mismatch); run text-only
    // gracefully.
    mmproj_path_.clear();
  }
#endif
}

bool LlamaSession::has_vision() const noexcept {
#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
  return (mtmd_ctx_ != nullptr && mtmd_support_vision(mtmd_ctx_.get())) ||
         !mmproj_path_.empty();
#else
  return false;
#endif
}

namespace {

// The single sequence this session uses (R6: one logical sequence; the prefix /
// anchored / tail segments are just position ranges within it).
constexpr llama_seq_id kSeqId = 0;

// Decode a span of tokens [tokens, tokens+n) at the current end of the
// sequence, requesting logits only for the LAST token (the usual prefill
// convention: the sampler needs the logits following the final decoded token).
// `base_pos` is the position the first token in the span occupies. Returns the
// batch index whose logits were requested (the last token's slot). Throws
// LlamaError on failure.
//
// A llama_batch is filled by hand (rather than llama_batch_get_one, which the
// header itself flags as a transition helper to avoid) so positions, seq ids,
// and per-token logits flags are set explicitly and correctly.
int decode_span(llama_context *ctx, const llama_token *tokens, std::size_t n,
                std::size_t base_pos) {
  assert(n > 0 && "decode_span requires a non-empty span");
  const std::size_t max_batch = static_cast<std::size_t>(llama_n_batch(ctx));

  int last_idx = 0;
  std::size_t current_pos = base_pos;

  for (std::size_t offset = 0; offset < n;) {
    const std::size_t chunk_len = std::min(n - offset, max_batch);
    const auto chunk_tok = static_cast<std::int32_t>(chunk_len);

    // embd = 0 (we supply token ids, not embeddings); n_seq_max = 1 (single
    // seq).
    LlamaBatch batch(chunk_tok, /*embd=*/0, /*n_seq_max=*/1);
    llama_batch &b = batch.get();

    for (std::int32_t i = 0; i < chunk_tok; ++i) {
      b.token[i] = tokens[offset + i];
      b.pos[i] = static_cast<llama_pos>(current_pos + i);
      b.n_seq_id[i] = 1;
      b.seq_id[i][0] = kSeqId;
      b.logits[i] = 0; // logits not needed for interior prefill tokens
    }
    b.n_tokens = chunk_tok;

    // Request logits only for the final token of the entire decoded span
    const bool is_final_chunk = (offset + chunk_len == n);
    if (is_final_chunk) {
      const std::int32_t last = chunk_tok - 1;
      b.logits[last] = 1;
      last_idx = last;
    }

    const std::int32_t rc = llama_decode(ctx, b);
    if (rc != 0) {
      // rc > 0 is a non-fatal warning (e.g. could not find a KV slot), rc < 0
      // is a hard failure; either way the append did not land cleanly, so
      // surface a typed decode_failed rather than advancing the position past a
      // bad decode.
      throw aquila::LlamaError("decode_failed",
                               "llama_decode returned " + std::to_string(rc) +
                                   " for a " + std::to_string(chunk_tok) +
                                   "-token batch");
    }

    offset += chunk_len;
    current_pos += chunk_len;
  }

  return last_idx;
}

#if defined(AQUILA_HAS_MTMD) && AQUILA_HAS_MTMD
std::vector<std::uint8_t> decode_base64_bytes(std::string_view encoded) {
  static constexpr std::array<int, 256> kDec = []() {
    std::array<int, 256> table{};
    table.fill(-1);
    for (int i = 0; i < 26; ++i) {
      table['A' + i] = i;
      table['a' + i] = 26 + i;
    }
    for (int i = 0; i < 10; ++i) {
      table['0' + i] = 52 + i;
    }
    table['+'] = 62;
    table['-'] = 62;
    table['/'] = 63;
    table['_'] = 63;
    return table;
  }();

  // Strip optional "data:<mime>;base64," URI prefix
  if (encoded.rfind("data:", 0) == 0) {
    const std::size_t marker = encoded.find(";base64,");
    if (marker != std::string_view::npos) {
      encoded.remove_prefix(marker + 8);
    }
  }

  std::vector<std::uint8_t> out;
  out.reserve((encoded.size() * 3) / 4);
  int val = 0;
  int valb = -8;
  for (unsigned char c : encoded) {
    if (std::isspace(c) || c == '=')
      continue;
    const int d = kDec[c];
    if (d < 0) {
      throw aquila::LlamaError(
          "invalid_request",
          "invalid base64 character in multimodal image payload");
    }
    val = (val << 6) + d;
    valb += 6;
    if (valb >= 0) {
      out.push_back(static_cast<std::uint8_t>((val >> valb) & 0xFF));
      valb -= 8;
    }
  }
  if (out.empty()) {
    throw aquila::LlamaError("invalid_request",
                             "empty base64 payload for multimodal image");
  }
  return out;
}

struct MtmdBitmapGuard {
  mtmd_bitmap *bmp = nullptr;
  MtmdBitmapGuard() = default;
  explicit MtmdBitmapGuard(mtmd_bitmap *b) : bmp(b) {}
  MtmdBitmapGuard(const MtmdBitmapGuard &) = delete;
  MtmdBitmapGuard &operator=(const MtmdBitmapGuard &) = delete;
  MtmdBitmapGuard(MtmdBitmapGuard &&o) noexcept : bmp(o.bmp) {
    o.bmp = nullptr;
  }
  MtmdBitmapGuard &operator=(MtmdBitmapGuard &&o) noexcept {
    if (this != &o) {
      if (bmp != nullptr)
        mtmd_bitmap_free(bmp);
      bmp = o.bmp;
      o.bmp = nullptr;
    }
    return *this;
  }
  ~MtmdBitmapGuard() {
    if (bmp != nullptr)
      mtmd_bitmap_free(bmp);
  }
};

struct MtmdChunksGuard {
  mtmd_input_chunks *chunks = nullptr;
  explicit MtmdChunksGuard(mtmd_input_chunks *c) : chunks(c) {}
  MtmdChunksGuard(const MtmdChunksGuard &) = delete;
  MtmdChunksGuard &operator=(const MtmdChunksGuard &) = delete;
  ~MtmdChunksGuard() {
    if (chunks != nullptr)
      mtmd_input_chunks_free(chunks);
  }
};
#endif

} // namespace

std::size_t LlamaSession::decode_text(const std::string &text) {
  const llama_vocab *v = vocab();

  // First pass: ask for the token count (a negative return is -count). BOS is
  // added only at the very start of the sequence; special/control tokens
  // emitted by an already-applied chat template are parsed, not treated as
  // literal text.
  const bool add_special = (pos_ == 0);
  const auto text_len = static_cast<std::int32_t>(text.size());
  const std::int32_t needed =
      llama_tokenize(v, text.data(), text_len, nullptr, 0, add_special,
                     /*parse_special=*/true);

  // needed is the (negative of the) token count; 0 means the text produced no
  // tokens (e.g. an empty string) -- nothing to decode, a degenerate request.
  const std::int32_t n_tokens = (needed < 0) ? -needed : needed;
  if (n_tokens == 0) {
    throw LlamaError("invalid_request",
                     "text tokenized to zero tokens (nothing to decode)");
  }

  std::vector<llama_token> tokens(static_cast<std::size_t>(n_tokens));
  const std::int32_t got = llama_tokenize(v, text.data(), text_len,
                                          tokens.data(), n_tokens, add_special,
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
    throw LlamaError("context_overflow",
                     "appending " + std::to_string(tokens.size()) +
                         " tokens at position " + std::to_string(pos_) +
                         " would exceed n_ctx=" + std::to_string(n_ctx_));
  }

  decode_span(ctx_.get(), tokens.data(), tokens.size(), pos_);

  tokens_.insert(tokens_.end(), tokens.begin(),
                 tokens.end()); // history for reprime
  pos_ += tokens.size();
  prefill_tokens_ += tokens.size();
  logits_fresh_ = true; // the just-decoded final token's logits are current
  return tokens.size();
}

std::size_t
LlamaSession::decode_multimodal(const std::string &templated_text,
                                const std::vector<std::string> &images) {
  if (images.empty()) {
    return decode_text(templated_text);
  }
#if !defined(AQUILA_HAS_MTMD) || !AQUILA_HAS_MTMD
  throw LlamaError("invalid_request",
                   "multimodal support (libmtmd) is not compiled in");
#else
  ensure_vision_loaded();
  if (mtmd_ctx_ == nullptr || !mtmd_support_vision(mtmd_ctx_.get())) {
    throw LlamaError("invalid_request",
                     "vision projector not loaded; specify --mmproj or place a "
                     "matching mmproj*.gguf alongside the model");
  }

  const mtmd_helper_init_opt opt = mtmd_helper_init_opt_default();
  std::vector<MtmdBitmapGuard> guards;
  guards.reserve(images.size());
  std::vector<const mtmd_bitmap *> raw_bitmaps;
  raw_bitmaps.reserve(images.size());

  for (const std::string &img : images) {
    std::error_code ec;
    mtmd_helper_bitmap_wrapper wrapped{};
    if (img.size() <= 4096 && img.rfind("data:", 0) != 0 &&
        std::filesystem::is_regular_file(std::filesystem::path(img), ec)) {
      wrapped = mtmd_helper_bitmap_init_from_file(mtmd_ctx_.get(), img.c_str(),
                                                  /*placeholder=*/false, opt);
    } else {
      const auto bytes = decode_base64_bytes(img);
      wrapped = mtmd_helper_bitmap_init_from_buf(mtmd_ctx_.get(), bytes.data(),
                                                 bytes.size(),
                                                 /*placeholder=*/false, opt);
    }
    (void)wrapped.video_ctx;
    if (wrapped.bitmap == nullptr) {
      throw LlamaError(
          "invalid_request",
          "failed to decode image input (supported: PNG, JPEG, BMP, GIF)");
    }
    raw_bitmaps.push_back(wrapped.bitmap);
    guards.emplace_back(wrapped.bitmap);
  }

  MtmdChunksGuard chunks(mtmd_input_chunks_init());
  if (chunks.chunks == nullptr) {
    throw LlamaError("decode_failed", "mtmd_input_chunks_init returned null");
  }

  mtmd_input_text text_in{};
  text_in.text = templated_text.c_str();
  text_in.text_len = templated_text.size();
  text_in.add_special = (pos_ == 0);
  text_in.parse_special = true;

  const std::int32_t tok_rc =
      mtmd_tokenize(mtmd_ctx_.get(), chunks.chunks, &text_in,
                    raw_bitmaps.data(), raw_bitmaps.size());
  if (tok_rc != 0) {
    throw LlamaError("invalid_request", "mtmd_tokenize failed with code " +
                                            std::to_string(tok_rc));
  }

  const llama_pos n_pos_needed = mtmd_helper_get_n_pos(chunks.chunks);
  const std::size_t n_tok_needed = mtmd_helper_get_n_tokens(chunks.chunks);
  if (n_pos_needed <= 0 || n_tok_needed == 0) {
    throw LlamaError("invalid_request",
                     "multimodal input produced zero tokens");
  }
  if (pos_ + static_cast<std::size_t>(n_pos_needed) > n_ctx_) {
    throw LlamaError("context_overflow",
                     "multimodal append of " + std::to_string(n_pos_needed) +
                         " positions at " + std::to_string(pos_) +
                         " would exceed n_ctx=" + std::to_string(n_ctx_));
  }

  llama_pos new_n_past = static_cast<llama_pos>(pos_);
  const std::int32_t eval_rc =
      mtmd_helper_eval_chunks(mtmd_ctx_.get(), ctx_.get(), chunks.chunks,
                              static_cast<llama_pos>(pos_), kSeqId, n_batch_,
                              /*logits_last=*/true, &new_n_past);
  if (eval_rc != 0) {
    throw LlamaError("decode_failed",
                     "mtmd_helper_eval_chunks failed with code " +
                         std::to_string(eval_rc));
  }

  pos_ = static_cast<std::size_t>(new_n_past);
  // Keep logical token vector aligned with M-RoPE sequence positions using
  // LLAMA_TOKEN_NULL placeholders so pure-text suffix replay never crosses an
  // image boundary silently.
  tokens_.resize(pos_, LLAMA_TOKEN_NULL);
  prefill_tokens_ += n_tok_needed;
  logits_fresh_ = true;

  if (is_hybrid_or_recurrent_) {
    capture_snapshot();
  }
  return n_tok_needed;
#endif
}

int LlamaSession::decode_one(llama_token tok) {
  // One more token must still fit in the context window (Req 2.4).
  if (pos_ + 1 > n_ctx_) {
    throw LlamaError("context_overflow",
                     "decoding one token at position " + std::to_string(pos_) +
                         " would exceed n_ctx=" + std::to_string(n_ctx_));
  }

  const int logits_idx = decode_span(ctx_.get(), &tok, 1, pos_);
  tokens_.push_back(tok); // history for reprime
  pos_ += 1;
  prefill_tokens_ += 1;
  logits_fresh_ = true; // this token's logits are now current
  return logits_idx;    // always 0 for a one-token batch
}

void LlamaSession::capture_snapshot() const {
  if (!is_hybrid_or_recurrent_ || pos_ == 0) {
    return;
  }
  for (const auto &existing : snapshots_) {
    if (existing.pos == pos_) {
      return;
    }
  }

  const std::size_t sz = llama_state_seq_get_size(ctx_.get(), kSeqId);
  if (sz == 0) {
    return;
  }
  std::vector<std::uint8_t> buf(sz);
  const std::size_t written =
      llama_state_seq_get_data(ctx_.get(), buf.data(), buf.size(), kSeqId);
  if (written == 0) {
    return;
  }
  buf.resize(written);

  constexpr std::size_t kMaxSnapshots = 6;
  if (snapshots_.size() >= kMaxSnapshots) {
    // Preserve index 0 (earliest pinned prefix snapshot) and evict
    // second-oldest.
    snapshots_.erase(snapshots_.begin() + 1);
  }
  snapshots_.push_back(SeqSnapshot{pos_, tokens_, std::move(buf)});
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
  if (pos == old_end) {
    return;
  }

  const llama_memory_t mem = llama_get_memory(ctx_.get());
  if (!is_hybrid_or_recurrent_) {
    // Pure transformer KV cache supports arbitrary [pos, inf) range removal
    // directly.
    llama_memory_seq_rm(mem, kSeqId, static_cast<llama_pos>(pos), -1);
    pos_ = pos;
    tokens_.resize(pos);
    logits_fresh_ = false;
    return;
  }

  // Hybrid / GatedDeltaNet recurrent architectures cannot partially trim
  // recurrent state at arbitrary mid-sequence offsets (`seq_rm(seq, p0>0, -1)`
  // fails), EXCEPT full wipe `seq_rm(seq, 0, -1)`. Restore the nearest host
  // snapshot <= pos and replay the remaining text token delta without advancing
  // prefill_tokens_.
  if (pos == 0) {
    llama_memory_seq_rm(mem, kSeqId, 0, -1);
    pos_ = 0;
    tokens_.clear();
    snapshots_.erase(
        std::remove_if(snapshots_.begin(), snapshots_.end(),
                       [](const SeqSnapshot &s) { return s.pos > 0; }),
        snapshots_.end());
    logits_fresh_ = false;
    return;
  }

    const SeqSnapshot *best = nullptr;
    for (const auto &snap : snapshots_) {
      if (snap.pos <= pos && (best == nullptr || snap.pos > best->pos)) {
        best = &snap;
      }
    }

    const std::size_t base_pos = best != nullptr ? best->pos : 0;
    for (std::size_t i = base_pos; i < pos; ++i) {
      if (tokens_[i] == LLAMA_TOKEN_NULL) {
        throw LlamaError("decode_failed",
                         "cannot roll back inside a multimodal region without "
                         "a snapshot on hybrid model");
      }
    }

    llama_memory_seq_rm(mem, kSeqId, 0, -1);
    if (best != nullptr) {
      const std::size_t read_bytes = llama_state_seq_set_data(
          ctx_.get(), best->state.data(), best->state.size(), kSeqId);
      if (read_bytes == 0) {
        throw LlamaError(
            "decode_failed",
            "llama_state_seq_set_data failed while restoring hybrid snapshot");
      }
    }

    const std::size_t delta_len = pos - base_pos;
    if (delta_len > 0) {
      decode_span(ctx_.get(), tokens_.data() + base_pos, delta_len, base_pos);
      logits_fresh_ = true; // decode_span requested logits for tokens_[pos - 1]
    } else {
      // Exact snapshot hit does not serialize logit vectors; mark stale until
      // next generate/decode.
      logits_fresh_ = false;
    }

    pos_ = pos;
    tokens_.resize(pos);
    snapshots_.erase(
        std::remove_if(snapshots_.begin(), snapshots_.end(),
                       [pos](const SeqSnapshot &s) { return s.pos > pos; }),
        snapshots_.end());
  }

  void LlamaSession::ensure_logits_fresh() {
    if (logits_fresh_ || pos_ == 0) {
      return;
    }

    if (is_hybrid_or_recurrent_) {
      const llama_token last = tokens_.back();
      if (last == LLAMA_TOKEN_NULL) {
        throw LlamaError("decode_failed",
                         "cannot re-prime logits at a multimodal token "
                         "boundary on hybrid model");
      }
      // Roll back 1 position using the nearest earlier snapshot (at least pos
      // 0) and decode `last` once without counting toward prefill_tokens_.
      rollback_to(pos_ - 1);
      decode_span(ctx_.get(), &last, 1, pos_);
      tokens_.push_back(last);
      pos_ += 1;
      logits_fresh_ = true;
      return;
    }

    // Standard KV cache re-prime: remove the single KV cell at pos_-1 and
    // re-decode it.
    const llama_token last = tokens_.back();
    const auto last_pos = static_cast<llama_pos>(pos_ - 1);

    const llama_memory_t mem = llama_get_memory(ctx_.get());
    llama_memory_seq_rm(mem, kSeqId, last_pos, last_pos + 1);

    decode_span(ctx_.get(), &last, 1, pos_ - 1);
    logits_fresh_ = true;
  }

} // namespace aquila

#endif // AQUILA_HAS_LLAMACPP
