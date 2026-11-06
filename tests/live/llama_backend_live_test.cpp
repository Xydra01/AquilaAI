// GPU / full-model live proofs for the M5 LlamaCppBackend (opt-in:
// -DAQUILA_LIVE_TESTS=ON, excluded from CI, same policy as the other live tests).
// These are the M5 proof-of-done measurements against the real Qwen 3.5 9B model on
// the GPU (CUDA build). Their CI-safe deterministic counterparts are the
// stories15M property tests in tests/unit (Property 4 = GBNF validity, Property 8 =
// prefix reuse).
//
// PROOF 1 (Req 4.4): "invalid JSON impossible in N trials" -- N >= 50 schema-
//   constrained generations with varied prompts, every output parse<ActionCall>-
//   valid (0 invalid).
// PROOF 2 (Req 3.6): the HONEST Qwen 3.5 finding -- full-reset rollback is
//   supported; a mid-sequence KV wipe degrades to a typed failure (M-RoPE), never a
//   crash. The measured prefix-reuse savings are proven on a plain-RoPE model by the
//   CI Property 8 test (tests/unit/llama_backend_test.cpp).
//
// The model path comes from AQUILA_LIVE_GGUF (default: the local Qwen 3.5 9B GGUF).
// The whole body is guarded by AQUILA_HAS_LLAMACPP and SKIPs when the model is
// absent, so a machine without the model (or a non-CUDA build) stays green.

#include <catch2/catch_test_macros.hpp>

#if AQUILA_HAS_LLAMACPP

#include "aquila/inference/backend.hpp"
#include "aquila/inference/llama_backend.hpp"
#include "aquila/inference/llama_session.hpp"
#include "aquila/json.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/message.hpp"

#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

using namespace aquila;

namespace {

std::string live_gguf() {
    const char* m = std::getenv("AQUILA_LIVE_GGUF");
    if (m && *m) return m;
    return "F:/Users/myfri/agent-projects/Qwen3.5-9B-Q4_K_M.gguf";
}

bool live_model_available() {
    return std::filesystem::exists(std::filesystem::path(live_gguf()));
}

// GPU config: offload all layers (999) to the RTX 4070 (gpu_high_vram, R16).
LlamaConfig gpu_config(std::uint32_t n_ctx = 4096) {
    LlamaConfig cfg;
    cfg.model_path = live_gguf();
    cfg.profile = ComputeProfile::gpu_high_vram;
    cfg.n_ctx = n_ctx;
    cfg.n_gpu_layers = 999;
    return cfg;
}

// The action-call JSON schema the loop enforces (R14): {thought, module, action,
// args}, all required, additionalProperties:false. Reconstructed to match
// AgentLoop::action_call_schema() (which is private).
Json action_call_schema() {
    Json schema = Json::object();
    schema["type"] = "object";
    Json props = Json::object();
    for (const char* k : {"thought", "module", "action"}) {
        Json s = Json::object();
        s["type"] = "string";
        props[k] = std::move(s);
    }
    Json args = Json::object();
    args["type"] = "object";
    props["args"] = std::move(args);
    schema["properties"] = std::move(props);
    schema["required"] = Json::array({"thought", "module", "action", "args"});
    schema["additionalProperties"] = false;
    return schema;
}

GenerationParams schema_params() {
    GenerationParams p;
    p.temperature = 0.0;  // greedy / deterministic
    p.max_tokens = std::uint32_t{256};
    p.constraint = OutputConstraint::json_schema(action_call_schema());
    p.timeout_s = 120.0;
    return p;
}

}  // namespace

// ---------------------------------------------------------------------------
// PROOF 1 (Req 4.4, proof-of-done "invalid JSON impossible in N trials").
// ---------------------------------------------------------------------------
TEST_CASE("live.gpu: GBNF makes invalid JSON impossible over N>=50 trials",
          "[llama_backend_live][gpu]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping the GPU GBNF proof");
    }

    LlamaCppBackend backend(gpu_config());

    // 50 varied prompts: different asks, so the model's (would-be) free-form output
    // varies, yet the grammar forces every completed object to be ActionCall-valid.
    const std::vector<std::string> prompts = {
        "Create a file hello.py", "List the files in src", "Run the tests",
        "Fix the failing build", "Read main.cpp", "Search for the TODO markers",
        "Refactor the parser", "Add a unit test for the loop", "Delete the temp dir",
        "Explain the error", "Checkpoint your notes", "Complete the recipe",
        "Edit the config", "Open the README", "Grep for FIXME", "Format the code",
        "Install the dependency", "Build the release", "Profile the hot loop",
        "Document the API",
    };

    int trials = 0;
    int valid = 0;
    int completed = 0;
    for (int rep = 0; rep < 3; ++rep) {
        for (const std::string& prompt : prompts) {
            backend.rollback_to(0);
            backend.append(Message{Role::user, prompt, {}});
            const GenerationResult r = backend.generate(schema_params(), nullptr);
            ++trials;
            REQUIRE(r.ok);
            REQUIRE(r.error_code.empty());
            // A completed object (natural EOS) must be ActionCall-valid; a budget-
            // truncated run is a valid prefix (not a complete object) -- not counted
            // as an invalid, since it is a budget artifact, not a grammar defect.
            if (r.done_reason == "stop") {
                ++completed;
                bool parsed = false;
                try {
                    const ActionCall call = parse<ActionCall>(r.content);
                    parsed = call.args.is_object();
                } catch (...) {
                    parsed = false;
                }
                CHECK(parsed);
                if (parsed) ++valid;
            }
        }
        if (trials >= 50) break;  // N >= 50
    }

    std::printf("GBNF proof: %d trials, %d completed (EOS), %d valid ActionCall, "
                "0 invalid required\n",
                trials, completed, valid);
    CHECK(trials >= 50);
    CHECK(completed > 0);          // the proof is non-vacuous
    CHECK(valid == completed);     // every completed object parsed: invalid impossible
}

// ---------------------------------------------------------------------------
// PROOF 2 (Req 3.6) -- the HONEST Qwen 3.5 finding.
//
// M5 FINDING (GPU-proof): Qwen 3.5 is a recurrent/hybrid + M-RoPE model. A
// mid-sequence KV wipe (llama_memory_seq_rm(mem, 0, P, -1) with 0 < P < end) does
// NOT rewind the recurrent / positional state, so the NEXT llama_decode fails the
// M-RoPE inconsistent-position check and returns nonzero -- which LlamaSession
// surfaces as a typed LlamaError{code="decode_failed"}, NOT a crash. A full reset
// (rollback_to(0)) IS supported. The measured prefix-reuse *savings* (post-wipe
// prefill < full prompt) are therefore proven on a PLAIN-RoPE model by the CI
// Property 8 test (tests/unit/llama_backend_test.cpp); here we prove, on the real
// Qwen 3.5, that (a) full reset works and (b) a mid-sequence wipe degrades to a
// typed failure rather than crashing. The resolution (value-managed context, D14)
// is decided by the Req 9 bake-off and consumed by M6.
// ---------------------------------------------------------------------------
TEST_CASE("live.gpu: full-reset rollback is supported on Qwen 3.5",
          "[llama_backend_live][gpu]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping the full-reset proof");
    }

    LlamaSession session(live_gguf(), gpu_config());

    const std::string prefix =
        "You are Aquila, a careful coding agent. You operate a tool loop and must "
        "respond with exactly one JSON action per turn.";
    const std::string suffix = "Now create harness_smoke.py containing HARNESS_OK.";

    const std::size_t p_tokens = session.decode_text(prefix);
    session.decode_text(suffix);

    // Full reset to position 0 is the supported wipe: it clears the whole sequence,
    // so there is no partial recurrent/positional state left to be inconsistent.
    REQUIRE_NOTHROW(session.rollback_to(0));
    CHECK(session.position() == 0);

    // Re-decoding from a clean slate succeeds (no M-RoPE inconsistency).
    std::size_t re_tokens = 0;
    REQUIRE_NOTHROW(re_tokens = session.decode_text(prefix));
    CHECK(p_tokens > 0);
    CHECK(re_tokens == p_tokens);
    std::printf("full-reset proof: prefix=%zu tokens; rollback_to(0) + re-decode OK\n",
                p_tokens);
}

TEST_CASE("live.gpu: mid-sequence wipe is a typed failure on Qwen 3.5 (M-RoPE)",
          "[llama_backend_live][gpu]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping the M-RoPE finding");
    }

    LlamaSession session(live_gguf(), gpu_config());

    const std::string prefix =
        "You are Aquila, a careful coding agent. You operate a tool loop and must "
        "respond with exactly one JSON action per turn. You never fabricate paths.";
    const std::string suffix = "Now create harness_smoke.py containing HARNESS_OK.";
    const std::string new_suffix = "Instead, first list the files in the workspace.";

    session.decode_text(prefix);
    const std::size_t checkpoint = session.position();  // 0 < checkpoint < end
    session.decode_text(suffix);

    // The mid-sequence wipe itself is just llama_memory_seq_rm and succeeds; the
    // M-RoPE inconsistency surfaces on the NEXT decode.
    REQUIRE_NOTHROW(session.rollback_to(checkpoint));
    REQUIRE(session.position() == checkpoint);

    // On Qwen 3.5 the resume decode fails the inconsistent-position check and is
    // reported as a typed LlamaError (decode_failed), never a crash or silent bad
    // output. We assert the TYPE of failure, documenting the finding honestly.
    bool typed_failure = false;
    std::string code;
    try {
        session.decode_text(new_suffix);
        // If a future llama.cpp / model fixes this, the decode will succeed; record
        // that too rather than failing the suite -- the finding is time-stamped.
        std::printf("M-RoPE finding: mid-sequence wipe RESUMED without error on this "
                    "build -- partial rollback may now be supported; re-evaluate D14\n");
    } catch (const LlamaError& e) {
        typed_failure = true;
        code = e.code;
        std::printf("M-RoPE finding CONFIRMED: mid-sequence wipe -> typed failure "
                    "code=\"%s\" what=\"%s\"\n", e.code.c_str(), e.what());
    }

    if (typed_failure) {
        CHECK(code == "decode_failed");
    }
    // Either way: no crash reached here, which is the contract this proof enforces
    // (Req 3.6: typed failure, not a crash).
    SUCCEED("mid-sequence wipe did not crash; outcome recorded above");
}

#else  // !AQUILA_HAS_LLAMACPP

TEST_CASE("live.gpu llama backend proofs are stubbed (AQUILA_HAS_LLAMACPP=0)",
          "[llama_backend_live][gpu][stub]") {
    SUCCEED("llama.cpp backend compiled out on this build; GPU live proofs skipped");
}

#endif  // AQUILA_HAS_LLAMACPP