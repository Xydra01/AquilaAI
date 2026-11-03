#include "aquila/types/recipe.hpp"

#include <algorithm>

namespace aquila {

using namespace json_io;

namespace {

template <class T>
Json to_json_array(const std::vector<T>& items) {
    Json out = Json::array();
    for (const auto& item : items) {
        Json e;
        to_json(e, item);
        out.push_back(std::move(e));
    }
    return out;
}

template <class T>
std::vector<T> from_json_array(const Json& value, const std::string& path) {
    return read_array<T>(value, path, [](const Json& e, const std::string& p) {
        T item;
        from_json(e, item, p);
        return item;
    });
}

void check_module_loaded(const std::vector<ModuleLoad>& loads, const std::string& module,
                         const std::string& path) {
    const bool loaded = std::any_of(loads.begin(), loads.end(),
                                    [&](const ModuleLoad& l) { return l.module == module; });
    if (!loaded) {
        throw SchemaError(path, "module '" + module + "' is not in load_modules");
    }
}

}  // namespace

void to_json(Json& j, const ModuleLoad& v) {
    j = Json::object();
    j["module"] = v.module;
    j["initial_state"] = v.initial_state;
    j["expose_actions"] = v.expose_actions;
}

void from_json(const Json& j, ModuleLoad& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"module", "initial_state", "expose_actions"});
    v.module = read_string(require(j, path, "module"), child_path(path, "module"));
    v.initial_state = read_object(require(j, path, "initial_state"), child_path(path, "initial_state"));
    v.expose_actions =
        read_string_array(require(j, path, "expose_actions"), child_path(path, "expose_actions"));
}

void to_json(Json& j, const HookCall& v) {
    j = Json::object();
    j["module"] = v.module;
    j["action"] = v.action;
    j["args"] = v.args;
}

void from_json(const Json& j, HookCall& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"module", "action", "args"});
    v.module = read_string(require(j, path, "module"), child_path(path, "module"));
    v.action = read_string(require(j, path, "action"), child_path(path, "action"));
    v.args = read_object(require(j, path, "args"), child_path(path, "args"));
}

void to_json(Json& j, const ValidationHook& v) {
    j = Json::object();
    j["module"] = v.module;
    j["action"] = v.action;
    j["must_succeed"] = v.must_succeed;
    j["on_failure_instruction"] = v.on_failure_instruction;
}

void from_json(const Json& j, ValidationHook& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"module", "action", "must_succeed", "on_failure_instruction"});
    v.module = read_string(require(j, path, "module"), child_path(path, "module"));
    v.action = read_string(require(j, path, "action"), child_path(path, "action"));
    v.must_succeed = read_bool(require(j, path, "must_succeed"), child_path(path, "must_succeed"));
    v.on_failure_instruction = read_string(require(j, path, "on_failure_instruction"),
                                           child_path(path, "on_failure_instruction"));
}

void to_json(Json& j, const RecipeCartridge& v) {
    j = Json::object();
    j["recipe_id"] = v.recipe_id;
    j["goal_template"] = v.goal_template;
    j["load_modules"] = to_json_array(v.load_modules);
    j["pre_llm_hooks"] = to_json_array(v.pre_llm_hooks);
    j["scratchpad_checklist"] = v.scratchpad_checklist;
    if (v.post_llm_validation_hook) {
        Json hook;
        to_json(hook, *v.post_llm_validation_hook);
        j["post_llm_validation_hook"] = std::move(hook);
    }
}

void from_json(const Json& j, RecipeCartridge& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path,
                   {"recipe_id", "goal_template", "load_modules", "pre_llm_hooks",
                    "scratchpad_checklist", "post_llm_validation_hook"});

    const auto id_path = child_path(path, "recipe_id");
    v.recipe_id = read_string(require(j, path, "recipe_id"), id_path);
    if (v.recipe_id.empty()) {
        throw SchemaError(id_path, "must not be empty");
    }
    v.goal_template = read_string(require(j, path, "goal_template"), child_path(path, "goal_template"));

    const auto loads_path = child_path(path, "load_modules");
    v.load_modules = from_json_array<ModuleLoad>(require(j, path, "load_modules"), loads_path);
    if (v.load_modules.empty()) {
        throw SchemaError(loads_path, "must contain at least one module");
    }

    v.pre_llm_hooks.clear();
    if (const auto it = j.find("pre_llm_hooks"); it != j.end()) {
        const auto hooks_path = child_path(path, "pre_llm_hooks");
        v.pre_llm_hooks = from_json_array<HookCall>(*it, hooks_path);
        for (std::size_t i = 0; i < v.pre_llm_hooks.size(); ++i) {
            check_module_loaded(v.load_modules, v.pre_llm_hooks[i].module,
                                child_path(index_path(hooks_path, i), "module"));
        }
    }

    v.scratchpad_checklist.clear();
    if (const auto it = j.find("scratchpad_checklist"); it != j.end()) {
        v.scratchpad_checklist = read_string_array(*it, child_path(path, "scratchpad_checklist"));
    }

    v.post_llm_validation_hook.reset();
    if (const auto it = j.find("post_llm_validation_hook"); it != j.end()) {
        const auto hook_path = child_path(path, "post_llm_validation_hook");
        ValidationHook hook;
        from_json(*it, hook, hook_path);
        check_module_loaded(v.load_modules, hook.module, child_path(hook_path, "module"));
        v.post_llm_validation_hook = std::move(hook);
    }
}

}  // namespace aquila
