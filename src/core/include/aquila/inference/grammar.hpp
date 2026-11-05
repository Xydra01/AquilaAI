#pragma once

// GrammarFactory (M5 task 3.1): turns an OutputConstraint into a GBNF grammar and
// then into a llama.cpp grammar sampler, so the action-call JSON schema is enforced
// by construction (R14: grammar, not heal).
//
// Everything that touches the llama.cpp C API (the grammar sampler, SamplerPtr) is
// guarded by `#if AQUILA_HAS_LLAMACPP`, matching llama_session.hpp. On the stub
// lanes (mingw-san / msvc-asan) grammar.cpp compiles to an empty TU; GrammarFactory
// is simply not declared there, so callers referencing it are themselves guarded.
//
// Task scope note (3.1): this declares gbnf_for (schema -> GBNF string, cached by
// the schema's canonical string) and make_grammar_sampler (GBNF -> SamplerPtr,
// returning a null SamplerPtr the caller maps to "invalid_request" when the grammar
// is unparseable). The backend that uses it (task 4) does not exist yet. The GBNF
// conversion routes through llama.cpp's common library (json_schema_to_grammar).

#include "aquila/inference/backend.hpp"        // OutputConstraint (shared M2 value type)
#include "aquila/inference/llama_session.hpp"  // SamplerPtr + RAII aliases (one definition)

#include <optional>
#include <string>

#if AQUILA_HAS_LLAMACPP
#include <llama.h>  // llama_vocab (forward-declared by value in the signature)
#include <unordered_map>
#endif

namespace aquila {

#if AQUILA_HAS_LLAMACPP

// Schema -> GBNF -> grammar sampler (Req 4). Caches GBNF by the schema's canonical
// string, since the action-call schema is constant across turns, so the conversion
// runs once per distinct schema for the life of the factory.
//
// The factory reuses SamplerPtr from llama_session.hpp (included above) so the RAII
// alias has a single definition shared with LlamaSession / the backend.
class GrammarFactory {
public:
    // Returns a GBNF string for the constraint, or nullopt for OutputConstraint::none
    // (Req 4.1, 4.2):
    //   none        -> nullopt (no grammar; the model is unconstrained).
    //   json_schema -> json_schema_to_grammar(schema).
    //   json        -> a generic-JSON grammar (any valid JSON value), obtained by
    //                  converting the permissive empty-object schema {} (which in
    //                  JSON Schema matches any instance).
    // The result is cached by the schema's canonical dump so a constant schema is
    // converted exactly once.
    [[nodiscard]] std::optional<std::string> gbnf_for(const OutputConstraint& constraint) const;

    // Builds a grammar sampler for `gbnf` against `vocab` via
    // llama_sampler_init_grammar(vocab, gbnf, "root"). Returns a null SamplerPtr
    // (default-constructed) when llama.cpp returns NULL for an unparseable grammar,
    // so the caller (task 4.2) maps it to error_code="invalid_request" (Req 4.3).
    // Never throws: a null return is the contract, not an exception.
    [[nodiscard]] SamplerPtr make_grammar_sampler(const llama_vocab* vocab,
                                                  const std::string& gbnf) const;

private:
    // Canonical-schema-string -> GBNF. mutable so gbnf_for stays const (it is a pure
    // query from the caller's view; the cache is an internal memo).
    mutable std::unordered_map<std::string, std::string> gbnf_cache_;
};

#endif  // AQUILA_HAS_LLAMACPP

}  // namespace aquila
