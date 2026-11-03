#include "fixtures.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cstdio>

using namespace aquila;

// Every single-byte deletion of the recipe fixture must either parse (and then be
// idempotent) or throw SchemaError; any other exception or a sanitizer report fails.
TEST_CASE("single-byte deletions of the recipe never escape as non-SchemaError") {
    const auto original =
        test::read_bytes(test::fixture_dir() / "json" / "recipe_refactor_cpp_component.json");
    std::size_t parsed = 0;
    std::size_t rejected = 0;
    for (std::size_t i = 0; i < original.size(); ++i) {
        std::string mutated = original;
        mutated.erase(i, 1);
        try {
            const auto recipe = parse<RecipeCartridge>(mutated);
            const auto once = to_canonical_string(recipe);
            CHECK(to_canonical_string(parse<RecipeCartridge>(once)) == once);
            ++parsed;
        } catch (const SchemaError&) {
            ++rejected;
        }
    }
    std::printf("mutations: %zu inputs, %zu parsed, %zu rejected with SchemaError\n",
                original.size(), parsed, rejected);
    CHECK(parsed + rejected == original.size());
    CHECK(rejected > 0);
}
