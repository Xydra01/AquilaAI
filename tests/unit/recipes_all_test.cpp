#include "aquila/agent/recipes.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/types/recipe.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace aquila;
using aquila::test::TempDir;

namespace {

std::string read_disk_recipe(const std::string& name) {
    const std::string path = std::string(AQUILA_RECIPE_DIR) + "/" + name;
    std::ifstream in(path, std::ios::binary);
    REQUIRE(in.is_open());
    std::ostringstream buf;
    buf << in.rdbuf();
    return buf.str();
}

}  // namespace

TEST_CASE("all 17 builtin recipes load, validate against builtin registry, and match on-disk JSON") {
    const auto all = all_builtin_recipes();
    REQUIRE(all.size() == 17);

    TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();
    ctx.max_output_chars = 4500;

    const auto registry = ModuleRegistry::builtin();

    for (const auto& recipe : all) {
        DYNAMIC_SECTION("Recipe: " << recipe.recipe_id) {
            const std::string filename = recipe.recipe_id + ".recipe.json";
            const std::string on_disk = read_disk_recipe(filename);

            // Byte-for-byte parity check in both directions
            CHECK(to_canonical_string(recipe) == on_disk);
            CHECK(parse<RecipeCartridge>(on_disk) == recipe);

            // Validates against ModuleRegistry::builtin() (all modules and actions exist and validate)
            CHECK_NOTHROW(registry.validate_recipe(recipe, ctx));
        }
    }
}

