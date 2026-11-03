#pragma once

#include "aquila/json.hpp"
#include "aquila/types/action.hpp"

#include <string>

namespace aquila {

// One executed action in the condenser's rolling tail (R6). The design doc's
// `tool_name` predates modules (S2); a module action is addressed by module + action.
struct ToolInteraction {
    std::string id;
    std::string module;
    std::string action;
    Json args = Json::object();
    ActionResult result;

    bool operator==(const ToolInteraction&) const = default;
};

void to_json(Json& j, const ToolInteraction& v);
void from_json(const Json& j, ToolInteraction& v, const std::string& path);

}  // namespace aquila
