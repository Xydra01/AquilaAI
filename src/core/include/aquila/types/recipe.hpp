#pragma once

#include "aquila/json.hpp"

#include <optional>
#include <string>
#include <vector>

namespace aquila {

struct ModuleLoad {
    std::string module;
    Json initial_state = Json::object();
    std::vector<std::string> expose_actions;

    bool operator==(const ModuleLoad&) const = default;
};

// A deterministic module call made by the recipe runner, not by the LLM, so it
// may target actions that are not in expose_actions.
struct HookCall {
    std::string module;
    std::string action;
    Json args = Json::object();

    bool operator==(const HookCall&) const = default;
};

struct ValidationHook {
    std::string module;
    std::string action;
    bool must_succeed = true;
    std::string on_failure_instruction;

    bool operator==(const ValidationHook&) const = default;
};

// Recipe "Configuration & Workflow Cartridge" (R12). `{{...}}` placeholders are
// kept verbatim. pre_llm_hooks and scratchpad_checklist may be omitted on input
// (they default to empty) but are always emitted.
struct RecipeCartridge {
    std::string recipe_id;
    std::string goal_template;
    std::vector<ModuleLoad> load_modules;
    std::vector<HookCall> pre_llm_hooks;
    std::vector<std::string> scratchpad_checklist;
    std::optional<ValidationHook> post_llm_validation_hook;

    bool operator==(const RecipeCartridge&) const = default;
};

void to_json(Json& j, const ModuleLoad& v);
void from_json(const Json& j, ModuleLoad& v, const std::string& path);

void to_json(Json& j, const HookCall& v);
void from_json(const Json& j, HookCall& v, const std::string& path);

void to_json(Json& j, const ValidationHook& v);
void from_json(const Json& j, ValidationHook& v, const std::string& path);

void to_json(Json& j, const RecipeCartridge& v);
void from_json(const Json& j, RecipeCartridge& v, const std::string& path);

}  // namespace aquila
