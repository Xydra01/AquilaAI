#pragma once

#include "aquila/modules/module.hpp"
#include "aquila/types/recipe.hpp"

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace aquila {

// Compile-time module registry (R13, Option A).
class ModuleRegistry {
public:
    using Factory = std::function<std::unique_ptr<IAgentModule>(const ModuleContext&)>;

    template <class T>
    void register_module(const std::string& id) {
        factories_[id] = [](const ModuleContext& ctx) { return std::make_unique<T>(ctx); };
    }

    [[nodiscard]] bool contains(const std::string& id) const;
    [[nodiscard]] std::vector<std::string> ids() const;

    // Throws std::invalid_argument for an unregistered id.
    [[nodiscard]] std::unique_ptr<IAgentModule> create(const std::string& id, const ModuleContext& ctx) const;

    // Checks a cartridge against the registered modules: every module exists,
    // every exposed and hook action exists, hook args match the action schema
    // (strings with {{placeholders}} are accepted as strings), and each
    // initial_state passes configure(). Throws SchemaError with the recipe path.
    void validate_recipe(const RecipeCartridge& recipe, const ModuleContext& ctx) const;

    // Registry with every built-in module.
    static ModuleRegistry builtin();

private:
    std::map<std::string, Factory> factories_;
};

}  // namespace aquila
