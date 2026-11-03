// Checks the types against the design document itself, not a copy of it.
#include "fixtures.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cstdio>
#include <sstream>
#include <vector>

using namespace aquila;

namespace {

struct Block {
    std::string text;
    std::size_t first_line = 0;  // 1-based line of the first JSON line
    std::size_t last_line = 0;
};

// The fenced block that follows the first line containing `marker`.
Block block_after(std::string_view marker) {
    std::istringstream in(test::read_bytes(AQUILA_DESIGN_DOC));
    std::vector<std::string> lines;
    for (std::string line; std::getline(in, line);) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        lines.push_back(std::move(line));
    }
    std::size_t i = 0;
    while (i < lines.size() && lines[i].find(marker) == std::string::npos) ++i;
    while (i < lines.size() && lines[i] != "```") ++i;
    const std::size_t open = i++;
    while (i < lines.size() && lines[i] != "```") ++i;
    REQUIRE(i < lines.size());

    Block b;
    b.first_line = open + 2;
    b.last_line = i;
    for (std::size_t k = open + 1; k < i; ++k) b.text += lines[k] + "\n";
    return b;
}

}  // namespace

TEST_CASE("design doc recipe (D:L433-477) parses and re-serializes") {
    const auto block = block_after("Here is what a Recipe JSON looks like");
    std::printf("design doc recipe block: lines %zu-%zu\n", block.first_line, block.last_line);
    CHECK(block.first_line == 434);
    CHECK(block.last_line == 476);

    const auto recipe = parse<RecipeCartridge>(block.text);
    const auto canonical = to_canonical_string(recipe);
    CHECK(Json::parse(canonical) == Json::parse(block.text));
    CHECK(canonical ==
          test::read_bytes(test::fixture_dir() / "json" / "recipe_refactor_cpp_component.json"));

    CHECK(recipe.recipe_id == "refactor_cpp_component");
    CHECK(recipe.load_modules.size() == 2);
    CHECK(recipe.load_modules[0].expose_actions.size() == 3);
    REQUIRE(recipe.post_llm_validation_hook.has_value());
    CHECK(recipe.post_llm_validation_hook->must_succeed);
}

TEST_CASE("design doc action call (D:L597-603) parses and re-serializes") {
    const auto block = block_after("enforce a compact \"thought\" field");
    std::printf("design doc action-call block: lines %zu-%zu\n", block.first_line, block.last_line);
    CHECK(block.first_line == 598);
    CHECK(block.last_line == 603);

    const auto call = parse<ActionCall>(block.text);
    const auto canonical = to_canonical_string(call);
    CHECK(Json::parse(canonical) == Json::parse(block.text));
    CHECK(canonical == test::read_bytes(test::fixture_dir() / "json" / "action_call_doc.json"));
}
