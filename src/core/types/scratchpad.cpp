#include "aquila/types/scratchpad.hpp"

namespace aquila {

using namespace json_io;

std::string_view to_string(ChecklistStatus status) noexcept {
    switch (status) {
        case ChecklistStatus::pending: return "pending";
        case ChecklistStatus::done: return "done";
        case ChecklistStatus::skipped: return "skipped";
    }
    return "pending";
}

namespace {

ChecklistStatus read_status(const Json& value, const std::string& path) {
    const auto text = read_string(value, path);
    for (const auto s : {ChecklistStatus::pending, ChecklistStatus::done, ChecklistStatus::skipped}) {
        if (text == to_string(s)) return s;
    }
    throw SchemaError(path, "unknown status '" + text + "' (expected pending|done|skipped)");
}

}  // namespace

void to_json(Json& j, const ChecklistItem& v) {
    j = Json::object();
    j["id"] = v.id;
    j["text"] = v.text;
    j["status"] = to_string(v.status);
}

void from_json(const Json& j, ChecklistItem& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"id", "text", "status"});
    v.id = read_string(require(j, path, "id"), child_path(path, "id"));
    v.text = read_string(require(j, path, "text"), child_path(path, "text"));
    v.status = read_status(require(j, path, "status"), child_path(path, "status"));
}

void to_json(Json& j, const AgentScratchpad& v) {
    j = Json::object();
    j["active_objective"] = v.active_objective;
    j["current_hypothesis"] = v.current_hypothesis;
    j["verified_facts"] = v.verified_facts;
    j["failed_approaches_do_not_repeat"] = v.failed_approaches_do_not_repeat;
    j["next_immediate_action"] = v.next_immediate_action;
    Json checklist = Json::array();
    for (const auto& item : v.checklist) {
        Json e;
        to_json(e, item);
        checklist.push_back(std::move(e));
    }
    j["checklist"] = std::move(checklist);
}

void from_json(const Json& j, AgentScratchpad& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path,
                   {"active_objective", "current_hypothesis", "verified_facts",
                    "failed_approaches_do_not_repeat", "next_immediate_action", "checklist"});
    v.active_objective =
        read_string(require(j, path, "active_objective"), child_path(path, "active_objective"));
    v.current_hypothesis =
        read_string(require(j, path, "current_hypothesis"), child_path(path, "current_hypothesis"));
    v.verified_facts =
        read_string_array(require(j, path, "verified_facts"), child_path(path, "verified_facts"));
    v.failed_approaches_do_not_repeat =
        read_string_array(require(j, path, "failed_approaches_do_not_repeat"),
                          child_path(path, "failed_approaches_do_not_repeat"));
    v.next_immediate_action = read_string(require(j, path, "next_immediate_action"),
                                          child_path(path, "next_immediate_action"));
    v.checklist = read_array<ChecklistItem>(
        require(j, path, "checklist"), child_path(path, "checklist"),
        [](const Json& e, const std::string& p) {
            ChecklistItem item;
            from_json(e, item, p);
            return item;
        });
}

}  // namespace aquila
