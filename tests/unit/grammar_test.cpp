// GrammarFactory tests (M5 task 3.2).
//
// Covers Requirement 4's pure schema->GBNF conversion and the typed (never fatal)
// grammar-failure contract:
//   Req 4.1 -- the action-call JSON schema maps to a NON-EMPTY GBNF string.
//   Req 4.2 -- OutputConstraint::none  -> nullopt (no grammar);
//              OutputConstraint::json  -> a non-empty (generic-JSON) GBNF.
//   Req 4.3 -- a malformed grammar yields a NULL SamplerPtr (the caller maps it to
//              error_code="invalid_request"), and NEVER crashes.
//   Caching -- gbnf_for twice with the same json_schema returns the identical string
//              (the action-call schema is constant across turns, converted once).
//
//   Property 5: Grammar failure is typed, not fatal -- for any malformed grammar,
//   make_grammar_sampler returns a null sampler and never throws/crashes (>=100
//   RapidCheck iterations over random junk GBNF). Validates: Requirements 4.3.
//
// STRUCTURE (mirrors llama_session_test.cpp, tasks 2.3/2.4):
//   - The whole llama-dependent body is `#if AQUILA_HAS_LLAMACPP`, with a trivially
//     -passing `#else` TEST_CASE on the stub lanes (mingw-san / msvc-asan) where the
//     backend (and GrammarFactory) are compiled out.
//   - GrammarFactory::gbnf_for needs NO model/vocab, so the none/json/json_schema/
//     cache cases ALWAYS run (even on a machine without the tiny GGUF fixture).
//   - make_grammar_sampler needs a real llama_vocab; the easiest honest way to get
//     one here is to load the tiny model via LlamaSession and call .vocab(). Those
//     cases SKIP(...) gracefully when AQUILA_TINY_GGUF is absent, exactly as 2.3/2.4
//     do -- so CI without the model, and the stub lanes, stay green.
//
// The schema under test is the ACTION-CALL schema AgentLoop enforces (R14). That
// helper is a private static on AgentLoop, so we build the byte-identical
// {thought, module, action, args} schema here (same shape agent_loop.cpp emits):
// four required string/object properties, additionalProperties:false.

#include <catch2/catch_test_macros.hpp>

#if AQUILA_HAS_LLAMACPP

#include "aquila/inference/backend.hpp"   // OutputConstraint (shared M2 value type)
#include "aquila/inference/grammar.hpp"   // GrammarFactory
#include "aquila/inference/llama_backend.hpp"  // LlamaConfig
#include "aquila/inference/llama_session.hpp"  // LlamaSession (for a real vocab)
#include "aquila/json.hpp"                // Json

#include <rapidcheck/catch.h>

#include <llama.h>  // llama_vocab

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>

using namespace aquila;

namespace {

// The tiny GGUF path injected by CMake (forward slashes); guard the define so this
// still compiles on an older configure that predates it.
#ifndef AQUILA_TINY_GGUF
#define AQUILA_TINY_GGUF ""
#endif

constexpr const char* kTinyGguf = AQUILA_TINY_GGUF;

// True when the local-cache model exists; when false the vocab-needing cases SKIP.
bool tiny_model_available() {
    return std::string(kTinyGguf).size() > 0 &&
           std::filesystem::exists(std::filesystem::path(kTinyGguf));
}

// A CPU config for loading the tiny model purely to obtain its vocab (no decode).
LlamaConfig cpu_config(std::uint32_t n_ctx = 256) {
    LlamaConfig cfg;
    cfg.model_path = kTinyGguf;
    cfg.profile = ComputeProfile::cpu_low_spec_edge;
    cfg.n_ctx = n_ctx;
    cfg.n_gpu_layers = 0;
    cfg.n_threads = std::uint32_t{2};
    return cfg;
}

// The byte-identical {thought, module, action, args} action-call schema AgentLoop
// enforces (R14). AgentLoop::action_call_schema() is private, so this reproduces the
// exact shape emitted by src/core/agent/agent_loop.cpp: all four fields required,
// thought/module/action as strings, args as an object, additionalProperties:false.
Json action_call_schema() {
    Json schema = Json::object();
    schema["type"] = "object";

    Json properties = Json::object();
    Json thought = Json::object();
    thought["type"] = "string";
    properties["thought"] = std::move(thought);
    Json module = Json::object();
    module["type"] = "string";
    properties["module"] = std::move(module);
    Json action = Json::object();
    action["type"] = "string";
    properties["action"] = std::move(action);
    Json args = Json::object();
    args["type"] = "object";
    properties["args"] = std::move(args);
    schema["properties"] = std::move(properties);

    schema["required"] = Json::array({"thought", "module", "action", "args"});
    schema["additionalProperties"] = false;
    return schema;
}

}  // namespace

// ---------------------------------------------------------------------------
// gbnf_for: the pure schema->GBNF conversion. NO model/vocab needed, so these run
// on every machine and every building lane.
// ---------------------------------------------------------------------------
TEST_CASE("gbnf_for maps the action-call schema to a non-empty GBNF",
          "[grammar][llamacpp]") {
    GrammarFactory factory;

    // Req 4.1: json_schema(action-call schema) -> a GBNF string that exists and is
    // non-empty (the grammar that makes the {thought,module,action,args} JSON
    // physically well-formed by construction).
    const std::optional<std::string> gbnf =
        factory.gbnf_for(OutputConstraint::json_schema(action_call_schema()));

    REQUIRE(gbnf.has_value());
    CHECK_FALSE(gbnf->empty());
}

TEST_CASE("gbnf_for returns nullopt for OutputConstraint::none",
          "[grammar][llamacpp]") {
    GrammarFactory factory;

    // Req 4.2: no constraint -> no grammar at all.
    const std::optional<std::string> gbnf = factory.gbnf_for(OutputConstraint::none());

    CHECK_FALSE(gbnf.has_value());
}

TEST_CASE("gbnf_for returns a non-empty generic-JSON GBNF for OutputConstraint::json",
          "[grammar][llamacpp]") {
    GrammarFactory factory;

    // Req 4.2: generic JSON -> a non-empty GBNF (any-valid-JSON grammar, from the
    // permissive empty-object schema {}).
    const std::optional<std::string> gbnf = factory.gbnf_for(OutputConstraint::json());

    REQUIRE(gbnf.has_value());
    CHECK_FALSE(gbnf->empty());
}

TEST_CASE("gbnf_for caches: the same json_schema yields the identical GBNF string",
          "[grammar][llamacpp]") {
    GrammarFactory factory;
    const OutputConstraint c = OutputConstraint::json_schema(action_call_schema());

    // The action-call schema is constant across turns; converting it twice must
    // return the same string (the second call is a cache hit -- we assert equality,
    // which is the observable contract; cache-hit timing is not asserted).
    const std::optional<std::string> first = factory.gbnf_for(c);
    const std::optional<std::string> second = factory.gbnf_for(c);

    REQUIRE(first.has_value());
    REQUIRE(second.has_value());
    CHECK(*first == *second);
    CHECK_FALSE(first->empty());
}

// A malformed JSON *schema* (a schema whose "type" is itself invalid) must NOT throw
// from gbnf_for -- the impl catches the converter failure and returns the
// unparseable-sentinel GBNF, so make_grammar_sampler on it later yields a null
// sampler (Req 4.3: a bad schema is a typed invalid_request at generate time, never
// a crash at conversion time). This exercises the gbnf_for side of 4.3 without a
// vocab.
TEST_CASE("gbnf_for does not throw on a malformed JSON schema",
          "[grammar][llamacpp]") {
    GrammarFactory factory;

    // A schema the converter cannot represent: "type" is a number, not a type name.
    Json bad = Json::object();
    bad["type"] = 12345;  // not a valid JSON-Schema type keyword

    std::optional<std::string> gbnf;
    REQUIRE_NOTHROW(gbnf = factory.gbnf_for(OutputConstraint::json_schema(bad)));
    // The sentinel is non-empty (an empty string would be a VALID empty grammar);
    // its unparseability surfaces as a null sampler, exercised in the vocab cases.
    REQUIRE(gbnf.has_value());
    CHECK_FALSE(gbnf->empty());
}

// ---------------------------------------------------------------------------
// make_grammar_sampler: needs a real llama_vocab. We get one by loading the tiny
// model (vocab only; no decode), so these SKIP when the fixture is absent.
// ---------------------------------------------------------------------------
TEST_CASE("make_grammar_sampler builds a non-null sampler for the action-call GBNF",
          "[grammar][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF (model not pinned "
             "for CI yet); skipping the vocab-backed sampler case");
    }

    LlamaSession session(kTinyGguf, cpu_config());
    const llama_vocab* vocab = session.vocab();
    REQUIRE(vocab != nullptr);

    GrammarFactory factory;
    const std::optional<std::string> gbnf =
        factory.gbnf_for(OutputConstraint::json_schema(action_call_schema()));
    REQUIRE(gbnf.has_value());

    // A valid GBNF -> a live grammar sampler (Req 4.1).
    const SamplerPtr sampler = factory.make_grammar_sampler(vocab, *gbnf);
    CHECK(sampler != nullptr);
}

TEST_CASE("make_grammar_sampler returns null for a malformed schema's GBNF",
          "[grammar][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF; skipping");
    }

    LlamaSession session(kTinyGguf, cpu_config());
    const llama_vocab* vocab = session.vocab();
    REQUIRE(vocab != nullptr);

    GrammarFactory factory;
    // Malformed schema -> gbnf_for returns the unparseable sentinel (no throw) ->
    // make_grammar_sampler returns a null SamplerPtr the caller maps to
    // invalid_request (Req 4.3). The whole path is non-fatal.
    Json bad = Json::object();
    bad["type"] = 12345;  // not a valid JSON-Schema type keyword
    const std::optional<std::string> gbnf =
        factory.gbnf_for(OutputConstraint::json_schema(bad));
    REQUIRE(gbnf.has_value());

    SamplerPtr sampler;
    REQUIRE_NOTHROW(sampler = factory.make_grammar_sampler(vocab, *gbnf));
    CHECK(sampler == nullptr);
}

// ---------------------------------------------------------------------------
// Property 5: Grammar failure is typed, not fatal.
// Feature: m5-llamacpp-backend, Property 5: Grammar failure is typed, not fatal --
// a malformed grammar never crashes and produces no sampler.
// Validates: Requirements 4.3
//
// For any random junk GBNF string, make_grammar_sampler returns a null SamplerPtr
// (llama_sampler_init_grammar returns NULL for an unparseable grammar) and NEVER
// throws/crashes. We generate random byte strings (printable + control bytes) that
// are overwhelmingly NOT valid GBNF; the contract is "no sampler, no crash". This is
// the reliable malformed path (feeding make_grammar_sampler a syntactically invalid
// grammar directly) that exactly exercises Req 4.3's unparseable-grammar -> null ->
// invalid_request mapping. It is cheap (grammar parse only, no decode), so >= 100
// iterations run fast on the vocab-only load.
// ---------------------------------------------------------------------------
TEST_CASE("Property 5: a malformed grammar yields a null sampler and never crashes",
          "[rapidcheck][grammar][llamacpp]") {
    if (!tiny_model_available()) {
        SKIP("tiny GGUF fixture not present at AQUILA_TINY_GGUF; skipping the "
             "vocab-backed Property 5");
    }

    LlamaSession session(kTinyGguf, cpu_config());
    const llama_vocab* vocab = session.vocab();
    REQUIRE(vocab != nullptr);

    GrammarFactory factory;

    rc::prop("make_grammar_sampler(vocab, junk) returns null without throwing",
             [&] {
                 // Random junk: 1..64 arbitrary bytes. A valid GBNF needs a `root`
                 // rule with `::=`; random bytes essentially never form one, so the
                 // sampler must come back null. (On the vanishingly unlikely chance
                 // a random string IS a valid grammar, the sampler would be non-null
                 // -- which is still "not a crash"; the property we assert below is
                 // the fatal-vs-typed one: never throws. We ALSO assert null for the
                 // dominant case via a crafted-invalid prefix to keep the signal.)
                 const std::string junk = *rc::gen::resize(
                     64, rc::gen::container<std::string>(rc::gen::arbitrary<char>()));

                 // A grammar guaranteed invalid: a bare control byte with no rule.
                 // Prepending it makes the whole string unparseable regardless of the
                 // random tail, so the sampler is deterministically null while the
                 // random tail still fuzzes the parser's byte handling for crashes.
                 const std::string malformed = std::string("\x01 ") + junk;

                 // The core of Property 5 is "typed, not fatal": this call must
                 // return (null), never throw/crash. Any exception would propagate
                 // out of the lambda and fail the property -- which is exactly the
                 // negative we are guarding against. No try/catch: a throw here IS
                 // the failure signal.
                 const SamplerPtr sampler = factory.make_grammar_sampler(vocab, malformed);

                 // Unparseable -> null sampler (-> caller maps to invalid_request).
                 RC_ASSERT(sampler == nullptr);
             });
}

#else  // !AQUILA_HAS_LLAMACPP

// Stub lanes (mingw-san / msvc-asan): GrammarFactory is compiled out, so there is
// nothing to test. One trivially-passing TEST_CASE keeps this TU in the suite
// without pulling in llama.cpp.
TEST_CASE("GrammarFactory tests are stubbed out on this lane (AQUILA_HAS_LLAMACPP=0)",
          "[grammar][llamacpp][stub]") {
    SUCCEED("llama.cpp backend is compiled out on this lane; grammar tests skipped");
}

#endif  // AQUILA_HAS_LLAMACPP
