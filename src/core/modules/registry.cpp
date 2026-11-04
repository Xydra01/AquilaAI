#include "aquila/modules/registry.hpp"

#include "aquila/modules/schema_check.hpp"

#include <set>
#include <stdexcept>

namespace aquila {

namespace {

const ActionSchema* find_action(const std::vector<ActionSchema>& actions, const std::string& name) {
    for (const auto& a : actions) {
        if (a.action_name == name) return &a;
    }
    return nullptr;
}

}  // namespace

bool ModuleRegistry::contains(const std::string& id) const {
    return factories_.count(id) != 0;
}

std::vector<std::string> ModuleRegistry::ids() const {
    std::vector<std::string> out;
    for (const auto& [id, _] : factories_) out.push_back(id);
    return out;
}

std::unique_ptr<IAgentModule> ModuleRegistry::create(const std::string& id, const ModuleContext& ctx) const {
    const auto it = factories_.find(id);
    if (it == factories_.end()) throw std::invalid_argument("unknown module '" + id + "'");
    return it->second(ctx);
}

void ModuleRegistry::validate_recipe(const RecipeCartridge& recipe, const ModuleContext& ctx) const {
    std::map<std::string, std::vector<ActionSchema>> actions;
    for (std::size_t i = 0; i < recipe.load_modules.size(); ++i) {
        const auto& load = recipe.load_modules[i];
        const auto base = json_io::index_path("/load_modules", i);
        if (!contains(load.module)) {
            throw SchemaError(json_io::child_path(base, "module"), "module '" + load.module + "' is not registered");
        }
        auto module = create(load.module, ctx);
        auto& acts = actions[load.module] = module->get_actions();
        for (std::size_t j = 0; j < load.expose_actions.size(); ++j) {
            if (find_action(acts, load.expose_actions[j]) == nullptr) {
                throw SchemaError(json_io::index_path(json_io::child_path(base, "expose_actions"), j),
                                  load.module + " has no action '" + load.expose_actions[j] + "'");
            }
        }
        try {
            module->configure(load.initial_state);
        } catch (const SchemaError& e) {
            throw SchemaError(json_io::child_path(base, "initial_state") + e.path(), e.reason());
        }
    }

    const auto check_hook = [&](const std::string& module, const std::string& action, const Json* args,
                                const std::string& base) {
        // A hook may only reference a module the recipe actually loaded (Req 5.4).
        // Surface a missing module as a SchemaError at the hook's JSON path rather
        // than letting the map lookup below throw std::out_of_range.
        const auto module_it = actions.find(module);
        if (module_it == actions.end()) {
            throw SchemaError(json_io::child_path(base, "module"),
                              "hook module '" + module + "' is not in load_modules");
        }
        const auto* schema = find_action(module_it->second, action);
        if (schema == nullptr) {
            throw SchemaError(json_io::child_path(base, "action"), module + " has no action '" + action + "'");
        }
        if (args != nullptr) check_schema(schema->parameters_json_schema, *args, json_io::child_path(base, "args"));
    };
    for (std::size_t k = 0; k < recipe.pre_llm_hooks.size(); ++k) {
        const auto& h = recipe.pre_llm_hooks[k];
        check_hook(h.module, h.action, &h.args, json_io::index_path("/pre_llm_hooks", k));
    }
    if (recipe.post_llm_validation_hook) {
        const auto& h = *recipe.post_llm_validation_hook;
        check_hook(h.module, h.action, nullptr, "/post_llm_validation_hook");
    }
}

}  // namespace aquila
