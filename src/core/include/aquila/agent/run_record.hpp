#pragma once

#include "aquila/json.hpp"
#include "aquila/types/tool_interaction.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace aquila {

// Loop-owned session metadata, deliberately NOT part of AgentScratchpad (D12).
// These are session fields, not LLM memory: the fields are drawn from Python's
// TaskRunContext (agent/core/run_state.py:95-220) but C++ never imports a Python
// run_state.json file — a run starts fresh (Req 6.3).
struct RunRecord {
    std::string task_id;
    std::string mode;          // e.g. "code"
    std::string instance_id;
    std::uint64_t step_index = 0;
    Json ground_truth = Json::object();        // free-form acceptance context
    std::optional<ToolInteraction> last_interaction;

    bool operator==(const RunRecord&) const = default;
};

void to_json(Json& j, const RunRecord& v);
void from_json(const Json& j, RunRecord& v, const std::string& path);  // round-trips byte-equal (Req 6.4)

}  // namespace aquila
