#pragma once

#include "aquila/json.hpp"

#include <cstdint>
#include <string>

namespace aquila {

// One LLM decision (R14): {"thought", "module", "action", "args"}.
struct ActionCall {
    std::string thought;
    std::string module;
    std::string action;
    Json args = Json::object();

    bool operator==(const ActionCall&) const = default;
};

// An action a module exposes (R10). parameters_json_schema must be an object.
struct ActionSchema {
    std::string action_name;
    std::string description;
    Json parameters_json_schema = Json::object();

    bool operator==(const ActionSchema&) const = default;
};

// Outcome of executing an action (R10).
struct ActionResult {
    bool success = false;
    std::string llm_facing_output;
    std::uint64_t token_estimate = 0;

    bool operator==(const ActionResult&) const = default;
};

void to_json(Json& j, const ActionCall& v);
void from_json(const Json& j, ActionCall& v, const std::string& path);

void to_json(Json& j, const ActionSchema& v);
void from_json(const Json& j, ActionSchema& v, const std::string& path);

void to_json(Json& j, const ActionResult& v);
void from_json(const Json& j, ActionResult& v, const std::string& path);

}  // namespace aquila
