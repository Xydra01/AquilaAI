#pragma once

#include "aquila/json.hpp"

#include <string>
#include <string_view>
#include <vector>

namespace aquila {

// Same values as Python's ChecklistItemState.status.
enum class ChecklistStatus { pending, done, skipped };

std::string_view to_string(ChecklistStatus status) noexcept;

struct ChecklistItem {
    std::string id;
    std::string text;
    ChecklistStatus status = ChecklistStatus::pending;

    bool operator==(const ChecklistItem&) const = default;
};

// The agent's self-notes (R7): a strict schema, no free-text notes field.
struct AgentScratchpad {
    std::string active_objective;
    std::string current_hypothesis;
    std::vector<std::string> verified_facts;
    std::vector<std::string> failed_approaches_do_not_repeat;
    std::string next_immediate_action;
    std::vector<ChecklistItem> checklist;

    bool operator==(const AgentScratchpad&) const = default;
};

void to_json(Json& j, const ChecklistItem& v);
void from_json(const Json& j, ChecklistItem& v, const std::string& path);

void to_json(Json& j, const AgentScratchpad& v);
void from_json(const Json& j, AgentScratchpad& v, const std::string& path);

}  // namespace aquila
