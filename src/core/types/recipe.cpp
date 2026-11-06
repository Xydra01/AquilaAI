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
    if (!v.include.empty()) {
        j["include"] = v.include;
    }
}

void from_json(const Json& j, RecipeCartridge& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path,
                   {"recipe_id", "goal_template", "load_modules", "pre_llm_hooks",
                    "scratchpad_checklist", "post_llm_validation_hook", "include"});

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

    v.include.clear();
    if (const auto it = j.find("include"); it != j.end()) {
        v.include = read_string_array(*it, child_path(path, "include"));
    }
}

namespace {

RecipeCartridge merge_cartridges(const RecipeCartridge& base, const RecipeCartridge& derived) {
    RecipeCartridge out;
    out.recipe_id = derived.recipe_id;
    out.goal_template = derived.goal_template.empty() ? base.goal_template : derived.goal_template;

    out.load_modules = base.load_modules;
    for (const auto& dm : derived.load_modules) {
        auto it = std::find_if(out.load_modules.begin(), out.load_modules.end(),
                               [&](const ModuleLoad& m) { return m.module == dm.module; });
        if (it != out.load_modules.end()) {
            if (!dm.initial_state.empty()) {
                it->initial_state = dm.initial_state;
            }
            for (const auto& act : dm.expose_actions) {
                if (std::find(it->expose_actions.begin(), it->expose_actions.end(), act) ==
                    it->expose_actions.end()) {
                    it->expose_actions.push_back(act);
                }
            }
        } else {
            out.load_modules.push_back(dm);
        }
    }

    out.pre_llm_hooks = base.pre_llm_hooks;
    for (const auto& hook : derived.pre_llm_hooks) {
        out.pre_llm_hooks.push_back(hook);
    }

    out.scratchpad_checklist = base.scratchpad_checklist;
    for (const auto& item : derived.scratchpad_checklist) {
        if (std::find(out.scratchpad_checklist.begin(), out.scratchpad_checklist.end(), item) ==
            out.scratchpad_checklist.end()) {
            out.scratchpad_checklist.push_back(item);
        }
    }

    if (derived.post_llm_validation_hook.has_value()) {
        out.post_llm_validation_hook = derived.post_llm_validation_hook;
    } else {
        out.post_llm_validation_hook = base.post_llm_validation_hook;
    }

    return out;
}

RecipeCartridge resolve_includes_impl(
    const RecipeCartridge& current,
    const std::function<std::optional<RecipeCartridge>(const std::string&)>& resolver,
    std::vector<std::string>& active_chain) {
    if (std::find(active_chain.begin(), active_chain.end(), current.recipe_id) != active_chain.end()) {
        throw SchemaError("/include", "cyclic include detected: " + current.recipe_id);
    }
    active_chain.push_back(current.recipe_id);

    if (current.include.empty()) {
        active_chain.pop_back();
        RecipeCartridge res = current;
        res.include.clear();
        return res;
    }

    RecipeCartridge merged_bases;
    bool has_base = false;
    for (const auto& inc_id : current.include) {
        if (std::find(active_chain.begin(), active_chain.end(), inc_id) != active_chain.end()) {
            throw SchemaError("/include", "cyclic include detected: " + inc_id);
        }
        auto inc_opt = resolver(inc_id);
        if (!inc_opt) {
            throw SchemaError("/include", "included recipe not found: " + inc_id);
        }
        RecipeCartridge resolved_inc = resolve_includes_impl(*inc_opt, resolver, active_chain);
        if (!has_base) {
            merged_bases = std::move(resolved_inc);
            has_base = true;
        } else {
            merged_bases = merge_cartridges(merged_bases, resolved_inc);
        }
    }

    active_chain.pop_back();

    RecipeCartridge final_res = merge_cartridges(merged_bases, current);
    final_res.recipe_id = current.recipe_id;
    final_res.goal_template =
        current.goal_template.empty() ? merged_bases.goal_template : current.goal_template;
    final_res.include.clear();

    for (const auto& hook : final_res.pre_llm_hooks) {
        check_module_loaded(final_res.load_modules, hook.module, "/pre_llm_hooks");
    }
    if (final_res.post_llm_validation_hook) {
        check_module_loaded(final_res.load_modules, final_res.post_llm_validation_hook->module,
                            "/post_llm_validation_hook");
    }

    return final_res;
}

}  // namespace

RecipeCartridge resolve_includes(
    const RecipeCartridge& root,
    const std::function<std::optional<RecipeCartridge>(const std::string&)>& resolver) {
    std::vector<std::string> active_chain;
    return resolve_includes_impl(root, resolver, active_chain);
}

}  // namespace aquila
