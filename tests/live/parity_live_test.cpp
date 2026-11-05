// Ollama <-> llama.cpp parity cross-check (M5 task 6.1, Req 8.4, R19).
//
// Compares LlamaCppBackend (direct, GBNF) against OllamaHttpBackend (HTTP, `format`
// JSON mode) on the SAME model family and the SAME action-call schema. A clean
// same-model comparison is possible because Ollama ships `llama3.2:latest` (the D15
// CPU base family) and we have the matching bartowski GGUF for the direct backend.
//
// The goal is NOT byte-identical output (different tokenizers of the same weights,
// different sampler plumbing, Ollama `format` vs GBNF) but a BEHAVIOR-contract match:
//   - both produce a schema-valid ActionCall (parse<ActionCall> + args.is_object),
//   - both are deterministic at a fixed seed (same backend, repeated, is stable).
// Any divergence (template framing, tokenizer, sampler defaults) is PRINTED as an
// explained finding (R19), not silently accepted.
//
// Opt-in: -DAQUILA_LIVE_TESTS=ON, excluded from CI. SKIPs when the GGUF or Ollama is
// absent, so machines without either stay green.

#include <catch2/catch_test_macros.hpp>

#if AQUILA_HAS_LLAMACPP

#include "aquila/inference/backend.hpp"
#include "aquila/inference/llama_backend.hpp"
#include "aquila/inference/ollama_backend.hpp"
#include "aquila/json.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/message.hpp"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <optional>
#include <string>

using namespace aquila;

namespace {

std::string parity_gguf() {
    if (const char* e = std::getenv("AQUILA_PARITY_GGUF"); e && *e) return e;
    return "D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf";
}
std::string parity_ollama_model() {
    if (const char* e = std::getenv("AQUILA_PARITY_OLLAMA_MODEL"); e && *e) return e;
    return "llama3.2:latest";
}
bool gguf_present() { return std::filesystem::exists(std::filesystem::path(parity_gguf())); }

Json action_call_schema() {
    Json s = Json::object();
    s["type"] = "object";
    Json props = Json::object();
    for (const char* k : {"thought", "module", "action"}) {
        Json p = Json::object(); p["type"] = "string"; props[k] = std::move(p);
    }
    Json args = Json::object(); args["type"] = "object";
    Json addl = Json::object(); addl["type"] = Json::array({"string", "integer", "boolean"});
    args["additionalProperties"] = std::move(addl);
    props["args"] = std::move(args);
    s["properties"] = std::move(props);
    s["required"] = Json::array({"thought", "module", "action", "args"});
    s["additionalProperties"] = false;
    return s;
}

GenerationParams schema_params() {
    GenerationParams p;
    p.temperature = 0.0;  // greedy: the most deterministic comparison point
    p.max_tokens = std::uint32_t{512};
    p.seed = std::int64_t{42};
    p.constraint = OutputConstraint::json_schema(action_call_schema());
    p.timeout_s = 120.0;
    return p;
}

std::optional<ActionCall> try_parse(const std::string& content) {
    try {
        ActionCall c = parse<ActionCall>(content);
        if (!c.args.is_object()) return std::nullopt;
        return c;
    } catch (...) { return std::nullopt; }
}

}  // namespace

TEST_CASE("live: llama.cpp vs Ollama parity on the action-call schema",
          "[parity][live]") {
    if (!gguf_present()) {
        SKIP("parity GGUF absent (AQUILA_PARITY_GGUF); skipping parity cross-check");
    }

    OllamaConfig ocfg;
    ocfg.model = parity_ollama_model();
    OllamaHttpBackend ollama(ocfg);
    if (!ollama.probe(3.0).has_value()) {
        SKIP("Ollama not reachable; skipping parity cross-check");
    }

    const Message prompt{Role::user,
        "Create a file named parity_check.txt. Respond with exactly one JSON action "
        "{thought, module, action, args}; put the filename in args.path."};

    // --- llama.cpp (direct, GBNF) ---
    LlamaConfig lcfg;
    lcfg.model_path = parity_gguf();
    lcfg.n_gpu_layers = (std::getenv("AQUILA_PARITY_GPU") ? 999 : 0);
    lcfg.n_ctx = 4096;
    LlamaCppBackend llama(lcfg);
    llama.append(prompt);
    const GenerationResult lr = llama.generate(schema_params(), nullptr);
    const auto lcall = lr.ok ? try_parse(lr.content) : std::nullopt;

    // --- Ollama (HTTP, format JSON) ---
    ollama.append(prompt);
    const GenerationResult orr = ollama.generate(schema_params(), nullptr);
    const auto ocall = orr.ok ? try_parse(orr.content) : std::nullopt;

    std::printf("PARITY: llama.cpp ok=%d parsed=%d | ollama ok=%d parsed=%d\n",
                int(lr.ok), int(lcall.has_value()), int(orr.ok), int(ocall.has_value()));
    if (lcall) std::printf("  llama.cpp action: module=%s action=%s\n",
                           lcall->module.c_str(), lcall->action.c_str());
    if (ocall) std::printf("  ollama    action: module=%s action=%s\n",
                           ocall->module.c_str(), ocall->action.c_str());

    // Behavior contract: both backends produce a schema-valid ActionCall. (Content
    // may differ -- different tokenizer/template/sampler -- which is the R19 finding
    // printed above, not a failure.)
    CHECK(lr.ok);
    CHECK(lcall.has_value());
    CHECK(orr.ok);
    CHECK(ocall.has_value());

    // Determinism: the llama.cpp backend repeated at the same seed is stable.
    llama.rollback_to(0);
    llama.append(prompt);
    const GenerationResult lr2 = llama.generate(schema_params(), nullptr);
    CHECK(lr2.content == lr.content);  // same seed, same backend -> identical
}

#else  // !AQUILA_HAS_LLAMACPP

TEST_CASE("live parity cross-check is stubbed (AQUILA_HAS_LLAMACPP=0)",
          "[parity][live][stub]") {
    SUCCEED("llama.cpp backend compiled out; parity cross-check skipped");
}

#endif
