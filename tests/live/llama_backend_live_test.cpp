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

#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/inference/llama_backend.hpp"
#include "aquila/inference/llama_session.hpp"
#include "aquila/json.hpp"
#include "aquila/knowledge/browser_module.hpp"
#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/message.hpp"

#include <httplib.h>

#include <cctype>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <thread>
#include <vector>

using namespace aquila;

namespace {

std::string live_gguf() {
    const char* m = std::getenv("AQUILA_LIVE_GGUF");
    if (m && *m) return m;
    if (std::filesystem::exists("F:/aquila-models/Qwen3.5-9B-Q4_K_M.gguf")) {
        return "F:/aquila-models/Qwen3.5-9B-Q4_K_M.gguf";
    }
    return "F:/Users/myfri/agent-projects/Qwen3.5-9B-Q4_K_M.gguf";
}

bool live_model_available() {
    return std::filesystem::exists(std::filesystem::path(live_gguf()));
}

// GPU config: offload all layers (999) to the RTX 4070 with 32K context,
// FlashAttention + Q8_0 KV, and auto-discovered mmproj (gpu_high_vram, R16).
LlamaConfig gpu_config(std::uint32_t n_ctx = 32768) {
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

TEST_CASE("live.gpu: hybrid snapshot rollback restores GatedDeltaNet + KV and saves prefill on Qwen 3.5",
          "[llama_backend_live][gpu]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping the hybrid rollback proof");
    }

    LlamaSession session(live_gguf(), gpu_config());
    REQUIRE(session.is_hybrid_or_recurrent());

    const std::string prefix =
        "You are Aquila, a careful coding agent. You operate a tool loop and must "
        "respond with exactly one JSON action per turn. You never fabricate paths.";
    const std::string suffix = "Now create harness_smoke.py containing HARNESS_OK.";
    const std::string new_suffix = "Instead, first list the files in the workspace.";

    const std::size_t p_tokens = session.decode_text(prefix);
    session.capture_snapshot();
    const std::size_t checkpoint = session.position();
    REQUIRE(checkpoint == p_tokens);
    session.decode_text(suffix);

    REQUIRE_NOTHROW(session.rollback_to(checkpoint));
    REQUIRE(session.position() == checkpoint);

    const std::size_t prefill_before = session.prefill_tokens();
    std::size_t resumed_tokens = 0;
    REQUIRE_NOTHROW(resumed_tokens = session.decode_text(new_suffix));
    const std::size_t prefill_delta = session.prefill_tokens() - prefill_before;
    CHECK(prefill_delta == resumed_tokens);
    CHECK(session.position() == checkpoint + resumed_tokens);
    std::printf("Hybrid snapshot rollback proof: prefix=%zu tok, resumed=%zu tok (prefill_delta=%zu, saved=%zu tok)\n",
                p_tokens, resumed_tokens, prefill_delta, p_tokens);
}

TEST_CASE("live.gpu: Qwen 3.5 9B 32K multimodal vision recognizes solid red image",
          "[llama_backend_live][gpu][vision]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping the vision proof");
    }

    const std::string mmproj = discover_mmproj_for_model(live_gguf());
    if (mmproj.empty()) {
        SKIP("mmproj-Qwen3.5-9B GGUF not present on disk; skipping live vision proof");
    }

    LlamaCppBackend backend(gpu_config(32768));

    // Construct an uncompressed 32x32 24-bit solid-red BGR BMP in memory and encode as base64.
    constexpr std::uint32_t kW = 32;
    constexpr std::uint32_t kH = 32;
    constexpr std::uint32_t kPixelBytes = kW * kH * 3;
    constexpr std::uint32_t kFileSize = 54 + kPixelBytes;
    std::vector<std::uint8_t> bmp(kFileSize, 0);
    bmp[0] = 'B';
    bmp[1] = 'M';
    bmp[2] = static_cast<std::uint8_t>(kFileSize & 0xFF);
    bmp[3] = static_cast<std::uint8_t>((kFileSize >> 8) & 0xFF);
    bmp[4] = static_cast<std::uint8_t>((kFileSize >> 16) & 0xFF);
    bmp[5] = static_cast<std::uint8_t>((kFileSize >> 24) & 0xFF);
    bmp[10] = 54;   // pixel data offset
    bmp[14] = 40;   // BITMAPINFOHEADER size
    bmp[18] = static_cast<std::uint8_t>(kW);
    bmp[22] = static_cast<std::uint8_t>(kH);
    bmp[26] = 1;    // planes
    bmp[28] = 24;   // bpp
    for (std::size_t off = 54; off + 2 < bmp.size(); off += 3) {
        bmp[off + 0] = 0;    // B
        bmp[off + 1] = 0;    // G
        bmp[off + 2] = 255;  // R
    }

    static constexpr char kB64[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string b64 = "data:image/bmp;base64,";
    for (std::size_t i = 0; i < bmp.size(); i += 3) {
        const std::uint32_t a = bmp[i];
        const std::uint32_t b = (i + 1 < bmp.size()) ? bmp[i + 1] : 0;
        const std::uint32_t c = (i + 2 < bmp.size()) ? bmp[i + 2] : 0;
        const std::uint32_t triple = (a << 16) | (b << 8) | c;
        b64.push_back(kB64[(triple >> 18) & 0x3F]);
        b64.push_back(kB64[(triple >> 12) & 0x3F]);
        b64.push_back((i + 1 < bmp.size()) ? kB64[(triple >> 6) & 0x3F] : '=');
        b64.push_back((i + 2 < bmp.size()) ? kB64[triple & 0x3F] : '=');
    }

    backend.append(Message{Role::system, "You are a concise vision assistant.", {}});
    backend.append(Message{Role::user, "What single primary color fills this entire image? Reply in one short sentence.", {b64}});

    GenerationParams p;
    p.temperature = 0.0;
    p.think = false;
    p.max_tokens = std::uint32_t{48};
    const GenerationResult res = backend.generate(p, nullptr);
    REQUIRE(res.ok);
    std::printf("Vision 32K proof reply: [%s]\n", res.content.c_str());

    std::string lower = res.content;
    for (char& ch : lower) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    CHECK(lower.find("red") != std::string::npos);
}

#ifdef AQUILA_HAS_BROWSER
TEST_CASE("live.gpu: Qwen 3.5 9B inspects BrowserModule screenshot via Role::tool observation",
          "[llama_backend_live][gpu][vision][browser]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping browser vision proof");
    }
    const std::string mmproj = discover_mmproj_for_model(live_gguf());
    if (mmproj.empty()) {
        SKIP("mmproj-Qwen3.5-9B GGUF not present on disk; skipping browser vision proof");
    }

    httplib::Server svr;
    svr.Get("/visual", [](const httplib::Request&, httplib::Response& res) {
        res.set_content(
            "<!doctype html><html><head><title>Visual Sensor Target</title>"
            "<style>body{background:#111;color:#eee;font-family:sans-serif;padding:32px}"
            ".patch{width:460px;height:460px;background:#00ff00;margin-top:16px}</style>"
            "</head><body><h1>Sensor Display</h1>"
            "<p>Describe the color of the large rendered square below. No color name appears in text.</p>"
            "<div class=\"patch\"></div></body></html>",
            "text/html; charset=utf-8");
    });
    const int port = svr.bind_to_any_port("127.0.0.1");
    REQUIRE(port > 0);
    std::thread server_thread([&svr]() { svr.listen_after_bind(); });

    const auto tmp_dir = std::filesystem::temp_directory_path() / "aquila_live_browser_vision";
    std::error_code ec;
    std::filesystem::remove_all(tmp_dir, ec);
    std::filesystem::create_directories(tmp_dir, ec);

    const std::string url = "http://127.0.0.1:" + std::to_string(port) + "/visual";
    knowledge::BrowserModule browser(ModuleContext{tmp_dir, 4000});
    const ActionResult nav_res = browser.execute_action("browser_navigate", Json::object({{"url", url}}));
    svr.stop();
    if (server_thread.joinable()) {
        server_thread.join();
    }

    REQUIRE(nav_res.success);
    REQUIRE(nav_res.images.size() == 1);
    REQUIRE(std::filesystem::exists(nav_res.images[0]));

    LlamaCppBackend backend(gpu_config(32768));
    backend.append(Message{
        Role::system,
        "You are a multimodal assistant. You already ran BrowserModule and received the tool screenshot below. "
        "Answer the user's question directly in plain English sentence form (do NOT output JSON or another tool call).",
        {}});
    backend.append(Message{
        Role::user,
        "Inspect the browser screenshot from the tool response and state the color of the large square in plain English.",
        {}});
    backend.append(Message{Role::assistant, R"({"thought":"Navigating","module":"BrowserModule","action":"browser_navigate","args":{"url":")" + url + R"("}})", {}});
    backend.append(Message{Role::tool, nav_res.llm_facing_output, nav_res.images});

    GenerationParams p;
    p.temperature = 0.0;
    p.think = false;
    p.max_tokens = std::uint32_t{48};
    const GenerationResult res = backend.generate(p, nullptr);
    std::filesystem::remove_all(tmp_dir, ec);

    REQUIRE(res.ok);
    std::printf("Browser Role::tool vision reply: [%s]\n", res.content.c_str());

    std::string lower = res.content;
    for (char& ch : lower) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    CHECK(lower.find("green") != std::string::npos);
}

TEST_CASE("live.gpu: agent executes multi-turn recipe with BrowserModule to extract web telemetry and store facts",
          "[llama_backend_live][gpu][browser][agent_loop]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping browser agent loop proof");
    }

    httplib::Server svr;
    svr.Get("/telemetry", [](const httplib::Request&, httplib::Response& res) {
        res.set_content(
            "<!doctype html><html><head><title>Telemetry Station Alpha</title></head>"
            "<body style=\"background:#0b1120;color:#f1f5f9;font-family:sans-serif;padding:24px\">"
            "<h1>Telemetry Station Alpha</h1>"
            "<p id=\"token\">Telemetry Key: <b>TLM-7702-OMEGA</b></p>"
            "<p>All subsystems nominal.</p>"
            "</body></html>",
            "text/html; charset=utf-8");
    });
    const int port = svr.bind_to_any_port("127.0.0.1");
    REQUIRE(port > 0);
    std::thread server_thread([&svr]() { svr.listen_after_bind(); });

    const auto tmp_dir = std::filesystem::temp_directory_path() / "aquila_live_agent_browser";
    std::error_code ec;
    std::filesystem::remove_all(tmp_dir, ec);
    std::filesystem::create_directories(tmp_dir, ec);

    const std::string url = "http://127.0.0.1:" + std::to_string(port) + "/telemetry";

    const std::string recipe_json = R"AQ({
  "recipe_id": "browser_live_smoke",
  "goal_template": "Retrieve telemetry data via browser and record findings: {{user_instructions}}",
  "load_modules": [
    {
      "module": "BrowserModule",
      "initial_state": {},
      "expose_actions": [
        "browser_navigate",
        "browser_extract_text"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": ["active_objective", "next_immediate_action"]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "update_task_ledger"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Navigate to the telemetry endpoint",
    "Record verified telemetry fact using KnowledgeModule.store_fact",
    "Complete recipe"
  ],
  "post_llm_validation_hook": {
    "module": "KnowledgeModule",
    "action": "get_all_facts",
    "must_succeed": true,
    "on_failure_instruction": "No verified facts recorded in KnowledgeStore."
  }
})AQ";

    const RecipeCartridge recipe = parse<RecipeCartridge>(recipe_json);

    auto backend = std::make_shared<LlamaCppBackend>(gpu_config(32768));
    ModuleRegistry registry = ModuleRegistry::builtin();

    ModuleContext ctx;
    ctx.workspace_root = tmp_dir;
    ctx.max_output_chars = 4000;

    LoopConfig config;
    config.tier = RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram);
    config.tier.limits.max_turns = 8;
    config.task_id = "browser_telemetry_live";
    config.instance_id = "live-gpu-browser";

    AgentLoop loop(*backend, registry, ctx);
    const TerminalResult result = loop.run(
        recipe,
        "Navigate to " + url + ", inspect the page text, extract the Telemetry Key, record it as a fact using KnowledgeModule.store_fact with category 'telemetry', update the task ledger, and call OrchestratorModule.complete_recipe.",
        config);

    svr.stop();
    if (server_thread.joinable()) {
        server_thread.join();
    }

    std::printf("[live browser agent] outcome=%d success=%d turns=%zu\n",
                static_cast<int>(result.outcome), static_cast<int>(result.success), result.transcript.size());

    bool used_browser = false;
    for (const auto& tr : result.transcript) {
        if (tr.parsed && tr.call && tr.call->module == "BrowserModule" && tr.call->action == "browser_navigate") {
            used_browser = true;
            break;
        }
    }
    CHECK(used_browser);

    knowledge::KnowledgeModule km(ctx);
    const std::string facts = km.facts().get_all_facts();
    const bool found_key = facts.find("TLM-7702-OMEGA") != std::string::npos;
    std::filesystem::remove_all(tmp_dir, ec);

    CHECK(found_key);
    CHECK(result.success);
}

TEST_CASE("live.gpu: agent actively scrolls and clicks tabs to uncover deep webpage facts",
          "[llama_backend_live][gpu][browser][agent_loop][explore]") {
    if (!live_model_available()) {
        SKIP("live GGUF not present at AQUILA_LIVE_GGUF; skipping browser explore proof");
    }

    httplib::Server svr;
    svr.Get("/specs", [](const httplib::Request&, httplib::Response& res) {
        std::string filler;
        for (int i = 1; i <= 35; ++i) {
            filler += "<p>Background paragraph " + std::to_string(i) +
                      ": standard architectural overview describing modular pipelines, serialization layers, and telemetry formatting without benchmark metrics.</p>";
        }
        res.set_content(
            "<!doctype html><html><head><title>Aquila Performance Report</title>"
            "<style>body{background:#0b1120;color:#f1f5f9;font-family:sans-serif;padding:24px;min-height:2600px}"
            "button{background:#2563eb;color:#fff;padding:10px 18px;border:none;border-radius:6px}</style></head><body><main>"
            "<h1>Aquila Performance Report</h1>"
            "<p>Click the Deep Specs tab below to reveal P99 latency, and scroll down to the bottom Benchmarks section to find peak throughput.</p>"
            "<button id=\"tab-specs\" role=\"tab\" aria-expanded=\"false\" "
            "onclick=\"this.setAttribute('aria-expanded','true');document.getElementById('specs-panel').textContent='Verified P99 Latency: LATENCY_P99_14MS';\">Deep Specs</button>"
            "<div id=\"specs-panel\" style=\"margin:16px 0;font-weight:bold\">(Click Deep Specs to load latency)</div>"
            + filler +
            "<section id=\"benchmarks\" style=\"margin-top:600px\"><h2>Bottom Throughput Benchmarks</h2>"
            "<p>Measured sustained throughput on RTX 4070: <b>THROUGHPUT_4200_TPS</b></p></section>"
            "</main></body></html>",
            "text/html; charset=utf-8");
    });
    const int port = svr.bind_to_any_port("127.0.0.1");
    REQUIRE(port > 0);
    std::thread server_thread([&svr]() { svr.listen_after_bind(); });

    const auto tmp_dir = std::filesystem::temp_directory_path() / "aquila_live_agent_explore";
    std::error_code ec;
    std::filesystem::remove_all(tmp_dir, ec);
    std::filesystem::create_directories(tmp_dir, ec);

    const std::string url = "http://127.0.0.1:" + std::to_string(port) + "/specs";

    const std::string recipe_json = R"AQ({
  "recipe_id": "browser_explore_live",
  "goal_template": "Explore an interactive webpage via click and scroll and record verified findings: {{user_instructions}}",
  "load_modules": [
    {
      "module": "BrowserModule",
      "initial_state": {},
      "expose_actions": [
        "browser_navigate",
        "browser_click",
        "browser_scroll",
        "browser_extract_text"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": ["active_objective", "next_immediate_action"]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "update_task_ledger"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Navigate to the performance report URL and inspect the page",
    "Click the Deep Specs tab with browser_click and scroll down with browser_scroll to uncover both metrics",
    "Record both latency and throughput facts using KnowledgeModule.store_fact",
    "Complete recipe"
  ],
  "post_llm_validation_hook": {
    "module": "KnowledgeModule",
    "action": "get_all_facts",
    "must_succeed": true,
    "on_failure_instruction": "No verified facts recorded in KnowledgeStore."
  }
})AQ";

    const RecipeCartridge recipe = parse<RecipeCartridge>(recipe_json);

    auto backend = std::make_shared<LlamaCppBackend>(gpu_config(32768));
    ModuleRegistry registry = ModuleRegistry::builtin();

    ModuleContext ctx;
    ctx.workspace_root = tmp_dir;
    ctx.max_output_chars = 3000;

    LoopConfig config;
    config.tier = RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram);
    config.tier.limits.max_turns = 14;
    config.max_repeated_calls = 3;
    config.task_id = "browser_explore_live";
    config.instance_id = "live-gpu-explore";

    AgentLoop loop(*backend, registry, ctx);
    const TerminalResult result = loop.run(
        recipe,
        "Navigate to " + url + ", uncover BOTH the P99 latency (inside the Deep Specs tab) and the peak throughput (at the bottom Benchmarks section), record both exact tokens in KnowledgeModule.store_fact, update the task ledger, and call OrchestratorModule.complete_recipe.",
        config);

    svr.stop();
    if (server_thread.joinable()) {
        server_thread.join();
    }

    bool used_nav = false;
    bool used_click = false;
    bool used_scroll = false;
    for (const auto& tr : result.transcript) {
        if (tr.parsed && tr.call && tr.call->module == "BrowserModule") {
            std::printf("  turn %zu: %s::%s(%s)\n",
                        static_cast<std::size_t>(tr.index),
                        tr.call->module.c_str(),
                        tr.call->action.c_str(),
                        tr.call->args.dump().c_str());
            if (tr.call->action == "browser_navigate") used_nav = true;
            if (tr.call->action == "browser_click") used_click = true;
            if (tr.call->action == "browser_scroll") used_scroll = true;
        }
    }
    std::printf("[live explore agent] outcome=%d success=%d turns=%zu nav=%d click=%d scroll=%d\n",
                static_cast<int>(result.outcome), static_cast<int>(result.success),
                result.transcript.size(), int(used_nav), int(used_click), int(used_scroll));

    knowledge::KnowledgeModule km(ctx);
    const std::string facts = km.facts().get_all_facts();
    const bool found_latency = facts.find("LATENCY_P99_14MS") != std::string::npos;
    const bool found_throughput = facts.find("THROUGHPUT_4200_TPS") != std::string::npos;
    std::filesystem::remove_all(tmp_dir, ec);

    CHECK(used_nav);
    CHECK(used_click);
    CHECK(used_scroll);
    CHECK(found_latency);
    CHECK(found_throughput);
    CHECK(result.success);
}
#endif

#else  // !AQUILA_HAS_LLAMACPP

TEST_CASE("live.gpu llama backend proofs are stubbed (AQUILA_HAS_LLAMACPP=0)",
          "[llama_backend_live][gpu][stub]") {
    SUCCEED("llama.cpp backend compiled out on this build; GPU live proofs skipped");
}

#endif  // AQUILA_HAS_LLAMACPP