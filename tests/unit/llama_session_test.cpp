// LlamaSession / LlamaCppBackend tests (M5 tasks 2.3 + 2.4).
//
// Task 2.3 -- Properties 1-3 for checkpoint/rollback over a REAL small-model CPU
//             session (stories15M, a Llama2 15M-param GGUF -- fast CPU decode):
//   Property 1: Rollback is exact (position restored AND a deterministic generate
//               from the restored position equals a generate from a fresh session
//               decoded only up to that position).           (Req 3.5)
//   Property 2: Rollback past the end throws std::out_of_range, session unchanged.
//                                                             (Req 3.4)
//   Property 3: position() == the sum of decode_text token counts == the KV's
//               llama_memory_seq_pos_max(mem,0)+1.            (Req 3.2)
//
// Task 2.4 -- RAII / no-leak lifecycle (construct+destroy on the small model; the
//             sanitizer lane linux-san is the real LSan/ASan/UBSan check) and
//             context_overflow (a prompt exceeding a tiny n_ctx yields the typed
//             LlamaError{"context_overflow"} with nothing decoded).  (Req 2.3, 2.4)
//
// GUARDING: the whole llama-dependent body is wrapped in `#if AQUILA_HAS_LLAMACPP`
// so this TU compiles to a trivially-passing placeholder TEST_CASE on the stub
// lanes (mingw-san / msvc-asan) where the backend is compiled out. The macro comes
// from the aquila_llamacpp INTERFACE target; tests/unit/CMakeLists.txt links it (or
// the define) into aquila_unit_tests so the guard resolves in this test TU.
//
// CI-SAFE MODEL FIXTURE: the tests load a tiny real-weight GGUF whose absolute path
// is injected by CMake as AQUILA_TINY_GGUF (a LOCAL CACHE outside the source tree).
// It is NOT pinned via FetchContent yet, so every llama TEST_CASE SKIPs gracefully
// (Catch2 SKIP(...)) when the file is absent -- CI on a machine without it, and the
// stub lanes, stay green. Pinning the model (URL + SHA256 FetchContent so CI can
// fetch it) is a documented FOLLOW-UP for the orchestrator; this task does not add
// a network fetch to CMake.

#include <catch2/catch_test_macros.hpp>

#if AQUILA_HAS_LLAMACPP

#include "aquila/inference/backend.hpp"
#include "aquila/inference/llama_backend.hpp"
#include "aquila/inference/llama_session.hpp"

#include <rapidcheck/catch.h>

#include <llama.h>

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using namespace aquila;

namespace {

// The tiny GGUF path is injected by CMake (forward slashes). Guard against the
// define being absent (older configure) so this still compiles.
#ifndef AQUILA_TINY_GGUF
#define AQUILA_TINY_GGUF ""
#endif

constexpr const char* kTinyGguf = AQUILA_TINY_GGUF;

// True when the local-cache model exists. When false, every llama TEST_CASE SKIPs
// rather than failing, so CI (and the stub lanes) stay green without the model.
bool tiny_model_available() {
    return std::string(kTinyGguf).size() > 0 &&
           std::filesystem::exists(std::filesystem::path(kTinyGguf));
}

// A modest CPU config for the property session: n_gpu_layers=0 (CPU), a small
// n_ctx (room for the generated short texts plus a few generated tokens), and a
// couple of threads so 100 property iterations stay fast on a 15M model.
LlamaConfig cpu_config(std::uint32_t n_ctx = 512) {
    LlamaConfig cfg;
    cfg.model_path = kTinyGguf;
    cfg.profile = ComputeProfile::cpu_low_spec_edge;
    cfg.n_ctx = n_ctx;
    cfg.n_gpu_layers = 0;
    cfg.n_threads = std::uint32_t{2};
    return cfg;
}

// Cross-check the logical position against the KV memory directly: an empty
// sequence reports pos_max == -1 (=> position 0); otherwise position == pos_max+1.
std::size_t kv_position(const LlamaSession& s) {
    const llama_memory_t mem = llama_get_memory(s.ctx());
    const llama_pos pos_max = llama_memory_seq_pos_max(mem, /*seq_id=*/0);
    return (pos_max < 0) ? std::size_t{0} : static_cast<std::size_t>(pos_max) + 1;
}

// Short printable-ASCII words (a-z plus space), length 1..24 bytes. Kept small so
// 100 property iterations over a real model decode stay fast; the alphabet stays
// well inside stories15M's byte-level vocab and tokenizes to a handful of tokens.
rc::Gen<std::string> short_text() {
    return rc::gen::suchThat(
        rc::gen::resize(
            24, rc::gen::container<std::string>(
                    rc::gen::elementOf(std::string("abcdefghijklmnopqrstuvwxyz ")))),
        [](const std::string& s) { return !s.empty(); });
}

// A deterministic, greedy, short generation (temperature 0 => argmax, Req 4.5) with
// no output constraint. Used by Property 1 to compare "generate from the restored
// position" against "generate from a fresh session decoded only up to that point".
GenerationParams greedy_params() {
    GenerationParams p;
    p.temperature = 0.0;        // greedy / deterministic
    p.max_tokens = std::uint32_t{8};
    p.seed = std::int64_t{0};   // fixed (unused at temp 0, but pinned for clarity)
    p.timeout_s = 30.0;
    return p;
}

}  // namespace

// ---------------------------------------------------------------------------
// Task 2.3 -- Property 1: Rollback is exact.
// Feature: m5-llamacpp-backend, Property 1: Rollback is exact -- after
// rollback_to(checkpoint) the position equals the checkpoint and a subsequent
// deterministic generate equals the no-extra-tokens generate.
// Validates: Requirements 3.5
// ---------------------------------------------------------------------------
TEST_CASE("Property 1: rollback is exact (position + deterministic generate)",
          "[rapidcheck][llama_session][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF (model not pinned "
             "for CI yet); skipping the real-model session property");
    }

    // One backend drives the "checkpoint then extra then rollback then generate"
    // arm; a second, FRESH backend decodes only the prefix and generates. Both are
    // loaded once and reused across iterations (model load is the slow part).
    auto base = std::make_unique<LlamaCppBackend>(cpu_config());

    rc::prop("rollback restores the position and the greedy continuation matches a "
             "fresh session decoded only to the checkpoint",
             [&] {
                 const std::string prefix = *short_text();
                 const std::string extra = *short_text();

                 // The backend's KV may hold leftovers from a prior iteration; reset
                 // to an empty sequence so each iteration starts clean.
                 base->rollback_to(0);
                 RC_ASSERT(base->mark_checkpoint() == std::size_t{0});

                 // Decode the prefix, mark the checkpoint, decode extra on top.
                 base->append(Message{Role::user, prefix});
                 const std::size_t checkpoint = base->mark_checkpoint();
                 base->append(Message{Role::user, extra});
                 RC_ASSERT(base->mark_checkpoint() > checkpoint);

                 // Roll back to the checkpoint: the position must be EXACTLY it.
                 base->rollback_to(checkpoint);
                 RC_ASSERT(base->mark_checkpoint() == checkpoint);

                 // Deterministic (greedy) generate from the restored position.
                 const GenerationResult after_rollback =
                     base->generate(greedy_params(), nullptr);

                 // A fresh session that only ever decoded the prefix, same greedy
                 // generate. Exactness of rollback means the KV is byte-for-byte the
                 // prefix-only state, so the continuations must be identical.
                 LlamaCppBackend fresh(cpu_config());
                 fresh.append(Message{Role::user, prefix});
                 RC_ASSERT(fresh.mark_checkpoint() == checkpoint);
                 const GenerationResult fresh_gen =
                     fresh.generate(greedy_params(), nullptr);

                 RC_ASSERT(after_rollback.ok == fresh_gen.ok);
                 RC_ASSERT(after_rollback.content == fresh_gen.content);
             });
}

// ---------------------------------------------------------------------------
// Task 2.3 -- Property 2: Rollback past the end throws, session unchanged.
// Feature: m5-llamacpp-backend, Property 2: Rollback past end throws
// std::out_of_range, session unchanged.
// Validates: Requirements 3.4
// ---------------------------------------------------------------------------
TEST_CASE("Property 2: rollback past the end throws and leaves the session unchanged",
          "[rapidcheck][llama_session][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF; skipping");
    }

    LlamaSession session(kTinyGguf, cpu_config());

    rc::prop("rollback_to(pos > position()) throws std::out_of_range and does not "
             "move the position",
             [&] {
                 // Reset to empty, decode a short text so the end is > 0.
                 session.rollback_to(0);
                 const std::string text = *short_text();
                 session.decode_text(text);

                 const std::size_t end = session.position();
                 // A strictly-past-the-end target (end+1 .. end+16).
                 const std::size_t overshoot =
                     end + static_cast<std::size_t>(*rc::gen::inRange<int>(1, 17));

                 RC_ASSERT_THROWS_AS(session.rollback_to(overshoot), std::out_of_range);

                 // Session unchanged: the position is still the pre-call end, and it
                 // still mirrors the KV memory exactly.
                 RC_ASSERT(session.position() == end);
                 RC_ASSERT(kv_position(session) == end);
             });
}

// ---------------------------------------------------------------------------
// Task 2.3 -- Property 3: Checkpoint equals the decoded token count.
// Feature: m5-llamacpp-backend, Property 3: Checkpoint equals decoded token count;
// mark_checkpoint tracks llama_memory_seq_pos_max.
// Validates: Requirements 3.2
// ---------------------------------------------------------------------------
TEST_CASE("Property 3: position equals the summed decoded token count and the KV max",
          "[rapidcheck][llama_session][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF; skipping");
    }

    // n_ctx large enough that a handful of short decodes never overflows (Property 3
    // is about counting, not the overflow guard, which Task 2.4 covers).
    LlamaSession session(kTinyGguf, cpu_config(/*n_ctx=*/1024));

    rc::prop("sum of decode_text token counts == position() == "
             "llama_memory_seq_pos_max(mem,0)+1",
             [&] {
                 session.rollback_to(0);
                 RC_ASSERT(session.position() == std::size_t{0});
                 RC_ASSERT(kv_position(session) == std::size_t{0});

                 // 1..4 short decode_text calls; sum the token counts they return.
                 const int n_chunks = *rc::gen::inRange<int>(1, 5);
                 std::size_t summed = 0;
                 for (int i = 0; i < n_chunks; ++i) {
                     const std::string chunk = *short_text();
                     const std::size_t appended = session.decode_text(chunk);
                     RC_ASSERT(appended > 0);  // short_text is non-empty => >=1 token
                     summed += appended;

                     // Invariant holds after EACH decode, not just at the end.
                     RC_ASSERT(session.position() == summed);
                     RC_ASSERT(kv_position(session) == summed);
                 }
             });
}

// ---------------------------------------------------------------------------
// Task 2.4 -- RAII / no-leak lifecycle (Req 2.3).
// A session constructed and destroyed in a scope must free every native handle.
// The linux-san lane (ASan+UBSan+LSan) is the real leak check; here we assert only
// that construction + a decode + destruction run cleanly and the handles are live.
// ---------------------------------------------------------------------------
TEST_CASE("LlamaSession RAII lifecycle: construct, use, and destroy cleanly",
          "[llama_session][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF; skipping");
    }

    // Construct + destroy across repeated scopes: a leaked model/context/sampler or
    // double-free shows up under LSan (linux-san) and the CRT debug heap (msvc).
    for (int i = 0; i < 3; ++i) {
        LlamaSession session(kTinyGguf, cpu_config(/*n_ctx=*/256));
        REQUIRE(session.ctx() != nullptr);
        REQUIRE(session.vocab() != nullptr);
        REQUIRE(session.n_ctx() > 0);

        // Touch the KV so the context actually allocates sequence state, then let
        // the scope end free everything via the RAII members (Req 2.3).
        const std::size_t appended = session.decode_text("the quick brown fox");
        REQUIRE(appended > 0);
        REQUIRE(session.position() == appended);
    }  // ~LlamaSession frees model/context here on every iteration

    SUCCEED("constructed and destroyed LlamaSession repeatedly with no crash/leak");
}

// ---------------------------------------------------------------------------
// Task 2.4 -- context_overflow (Req 2.4).
// A prompt whose token count exceeds the context window must raise the typed
// LlamaError{"context_overflow"} and decode NOTHING (position unchanged), never a
// silent truncation.
//
// NOTE on n_ctx sizing: llama.cpp pads the requested n_ctx up to a multiple of 256
// at context creation (GGML_PAD in llama-context.cpp) while deriving n_batch from
// the UN-padded request, so an extreme tiny request (e.g. 16) yields a context
// whose real n_ctx (256) is far larger than its n_batch (16). decode_text's
// overflow guard is defined against the (real, padded) n_ctx -- session.n_ctx() --
// per Req 2.4, so we size the prompt to exceed THAT reported value. (Requesting a
// value below the n_batch/n_ctx split would let a prompt slip past the n_ctx guard
// and hit llama_decode's internal n_batch assert, which is a separate single-decode
// bound, not the Req 2.4 context_overflow contract.) We request 256 (a clean
// multiple, matching stories15M's trained context) and overflow it outright.
// ---------------------------------------------------------------------------
TEST_CASE("decode_text raises a typed context_overflow and decodes nothing",
          "[llama_session][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF; skipping");
    }

    LlamaSession session(kTinyGguf, cpu_config(/*n_ctx=*/256));
    const std::size_t before = session.position();
    const std::size_t ctx = session.n_ctx();  // the real (padded) window
    REQUIRE(ctx > 0);

    // Build a prompt guaranteed to tokenize past the context window: repeat a short
    // multi-token word more than n_ctx times, so even a 1-token-per-word tokenizer
    // produces well over n_ctx tokens. "overflow " is several tokens on its own.
    std::string long_prompt;
    long_prompt.reserve((ctx + 8) * 9);
    for (std::size_t i = 0; i < ctx + 8; ++i) {
        long_prompt += "overflow ";
    }

    bool threw_overflow = false;
    try {
        session.decode_text(long_prompt);
    } catch (const LlamaError& e) {
        threw_overflow = (e.code == "context_overflow");
    }

    CHECK(threw_overflow);
    // Nothing was decoded: the position is exactly where it started (Req 2.4).
    CHECK(session.position() == before);
    CHECK(kv_position(session) == before);
}

#else  // !AQUILA_HAS_LLAMACPP

// Stub lanes (mingw-san / msvc-asan): the backend is compiled out, so there is no
// LlamaSession to test. A single trivially-passing TEST_CASE keeps this TU in the
// suite (so the file is always compiled and linked) without pulling in llama.cpp.
TEST_CASE("LlamaSession tests are stubbed out on this lane (AQUILA_HAS_LLAMACPP=0)",
          "[llama_session][llamacpp][stub]") {
    SUCCEED("llama.cpp backend is compiled out on this lane; session tests skipped");
}

#endif  // AQUILA_HAS_LLAMACPP
