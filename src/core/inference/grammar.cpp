// GrammarFactory implementation (M5 task 3.1).
//
// The ENTIRE translation unit is wrapped in `#if AQUILA_HAS_LLAMACPP` so it compiles
// to an empty object file on the stub lanes (mingw-san / msvc-asan), exactly like
// llama_session.cpp. This keeps the source list in src/core/CMakeLists.txt
// unconditional; the file is always compiled, just empty where the backend is
// stubbed.
//
// === nlohmann-type finding (the integration snag the task flagged) ===========
// The design sketch quotes an older llama.cpp API where json_schema_to_grammar took
// `const nlohmann::ordered_json&`. At the pinned tag (b12116) upstream has REPLACED
// that with its OWN pimpl JSON type: `json_schema_to_grammar(const common_json&,
// bool)` (common/json-schema-to-grammar.h), where common_json is a thin wrapper over
// a vendored nlohmann (common/json.h). So Aquila's `Json` (nlohmann::ordered_json)
// is NOT the type the function accepts -- they are different types entirely, not an
// ABI/version mismatch. The clean, type-safe bridge is therefore the round-trip the
// task anticipated: dump our Json to a canonical string and re-parse it with
// common_json::parse(). This never mixes the two nlohmann instances in one call, so
// there is no ODR/ABI hazard, and it is cheap because gbnf_for caches by that same
// dumped string (the action-call schema is converted once).

#include "aquila/inference/grammar.hpp"

#if AQUILA_HAS_LLAMACPP

// llama.cpp common library: the schema->GBNF converter and its JSON type. These
// headers live under common/ and are exposed SYSTEM by the aquila_llamacpp interface
// target, so our /W4 /WX never sees them.
#include <json-schema-to-grammar.h>  // json_schema_to_grammar(const common_json&, bool)
#include <json.h>                    // common_json, common_json::parse, common_json_error

#include <exception>
#include <string>

namespace aquila {

namespace {

// A deliberately-unparseable GBNF sentinel. When a schema cannot be converted (bad
// JSON, or a schema json_schema_to_grammar cannot represent), gbnf_for returns this
// instead of throwing, so make_grammar_sampler then gets NULL from
// llama_sampler_init_grammar and hands the caller a null SamplerPtr -> the backend
// reports error_code="invalid_request" at generate time (Req 4.3). It must be
// non-empty (an empty grammar string is a VALID empty grammar upstream, not an
// error) and syntactically invalid GBNF (a bare symbol with no "::=" rule).
constexpr const char* kUnparseableGbnf = "\x01 invalid grammar";

// Convert one JSON-schema string (our Json, dumped) into a GBNF grammar string.
// Routes through llama.cpp's common_json so the call matches the upstream signature
// at this tag (see the nlohmann-type finding above). common_json::parse throws
// common_json_error on malformed JSON; json_schema_to_grammar can throw on a schema
// it cannot represent. Both are caught here and turned into the unparseable sentinel
// so gbnf_for stays non-throwing and the failure surfaces as a null sampler (Req 4.3:
// a bad schema is a typed invalid_request at generate time, never a crash).
std::string schema_string_to_gbnf(const std::string& schema_json) {
    try {
        const common_json schema = common_json::parse(schema_json);
        return json_schema_to_grammar(schema);
    } catch (const std::exception&) {
        return kUnparseableGbnf;
    }
}

}  // namespace

std::optional<std::string> GrammarFactory::gbnf_for(const OutputConstraint& constraint) const {
    switch (constraint.kind) {
        case OutputConstraint::Kind::none:
            // No constraint -> no grammar; the model samples freely (Req 4.2).
            return std::nullopt;

        case OutputConstraint::Kind::json: {
            // Generic JSON: the empty-object schema {} matches ANY JSON value in
            // JSON Schema, so json_schema_to_grammar({}) is a correct any-JSON GBNF.
            // Routed through the same converter (and cache) as a real schema so the
            // one code path handles both. Cache key is the literal "{}".
            static const std::string kAnyJsonSchema = "{}";
            auto it = gbnf_cache_.find(kAnyJsonSchema);
            if (it == gbnf_cache_.end()) {
                it = gbnf_cache_.emplace(kAnyJsonSchema,
                                         schema_string_to_gbnf(kAnyJsonSchema))
                         .first;
            }
            return it->second;
        }

        case OutputConstraint::Kind::json_schema: {
            // Cache by the schema's canonical string: the action-call schema is
            // constant across turns, so it is converted to GBNF exactly once for the
            // life of the factory. dump() is the canonical key (ordered_json keeps
            // key order, so it is stable).
            const std::string key = constraint.schema.dump();
            auto it = gbnf_cache_.find(key);
            if (it == gbnf_cache_.end()) {
                it = gbnf_cache_.emplace(key, schema_string_to_gbnf(key)).first;
            }
            return it->second;
        }
    }

    // Unreachable: every enumerator is handled above. Returning nullopt keeps the
    // function total without an assertion that a /W4 build would flag as a possibly
    // unreachable path.
    return std::nullopt;
}

SamplerPtr GrammarFactory::make_grammar_sampler(const llama_vocab* vocab,
                                                const std::string& gbnf) const {
    // "root" is the start symbol json_schema_to_grammar emits (and the GBNF
    // convention). llama_sampler_init_grammar returns NULL when grammar_str fails to
    // parse; we wrap whatever it returns in SamplerPtr, so a NULL becomes a null
    // (default-constructed) SamplerPtr the caller maps to "invalid_request" (Req 4.3).
    // No throw: a null sampler is the documented contract for a bad grammar.
    return SamplerPtr(llama_sampler_init_grammar(vocab, gbnf.c_str(), "root"));
}

}  // namespace aquila

#endif  // AQUILA_HAS_LLAMACPP
