#include "aquila/types/task_ledger.hpp"

#include <algorithm>
#include <cctype>
#include <sstream>

namespace aquila {

using namespace json_io;

std::string_view to_string(LedgerStepStatus status) noexcept {
    switch (status) {
        case LedgerStepStatus::pending: return "pending";
        case LedgerStepStatus::in_progress: return "in_progress";
        case LedgerStepStatus::completed: return "completed";
        case LedgerStepStatus::blocked: return "blocked";
        case LedgerStepStatus::skipped: return "skipped";
    }
    return "pending";
}

std::string_view to_checkbox(LedgerStepStatus status) noexcept {
    switch (status) {
        case LedgerStepStatus::pending: return "[ ]";
        case LedgerStepStatus::in_progress: return "[/]";
        case LedgerStepStatus::completed: return "[x]";
        case LedgerStepStatus::blocked: return "[!]";
        case LedgerStepStatus::skipped: return "[-]";
    }
    return "[ ]";
}

LedgerStepStatus parse_ledger_status(std::string_view text) {
    std::string lower;
    lower.reserve(text.size());
    for (char c : text) {
        lower.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    if (lower == "completed" || lower == "done" || lower == "pass" || lower == "passed" || lower == "[x]" || lower == "x") {
        return LedgerStepStatus::completed;
    }
    if (lower == "in_progress" || lower == "active" || lower == "running" || lower == "working" || lower == "[/]" || lower == "/") {
        return LedgerStepStatus::in_progress;
    }
    if (lower == "blocked" || lower == "failed" || lower == "error" || lower == "[!]" || lower == "!") {
        return LedgerStepStatus::blocked;
    }
    if (lower == "skipped" || lower == "bypass" || lower == "bypassed" || lower == "[-]" || lower == "-") {
        return LedgerStepStatus::skipped;
    }
    return LedgerStepStatus::pending;
}

namespace {

std::string to_lower_string(std::string_view s) {
    std::string res;
    res.reserve(s.size());
    for (char c : s) {
        res.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return res;
}

}  // namespace

bool TaskLedger::all_mandatory_completed() const noexcept {
    if (steps.empty()) return true;
    for (const auto& step : steps) {
        if (step.status != LedgerStepStatus::completed && step.status != LedgerStepStatus::skipped) {
            return false;
        }
    }
    return true;
}

std::vector<std::string> TaskLedger::incomplete_steps() const {
    std::vector<std::string> res;
    for (std::size_t i = 0; i < steps.size(); ++i) {
        const auto& s = steps[i];
        if (s.status != LedgerStepStatus::completed && s.status != LedgerStepStatus::skipped) {
            res.push_back("Step " + std::to_string(i + 1) + " (" + s.id + "): " + s.description + " [" + std::string(to_string(s.status)) + "]");
        }
    }
    return res;
}

LedgerStep* TaskLedger::find_step(std::string_view query) {
    if (query.empty() || steps.empty()) return nullptr;

    const std::string q_str = to_lower_string(query);

    // 1. Try 1-based integer index, e.g. "1", "2"
    bool all_digits = true;
    for (char c : q_str) {
        if (!std::isdigit(static_cast<unsigned char>(c))) {
            all_digits = false;
            break;
        }
    }
    if (all_digits) {
        try {
            const auto idx = std::stoul(q_str);
            if (idx >= 1 && idx <= steps.size()) {
                return &steps[idx - 1];
            }
        } catch (...) {}
    }

    // 2. Try prefix "step_" followed by number, e.g. "step_1"
    if (q_str.rfind("step_", 0) == 0 && q_str.size() > 5) {
        try {
            const auto idx = std::stoul(q_str.substr(5));
            if (idx >= 1 && idx <= steps.size()) {
                return &steps[idx - 1];
            }
        } catch (...) {}
    }

    // 3. Exact ID match (case-insensitive)
    for (auto& s : steps) {
        if (to_lower_string(s.id) == q_str) {
            return &s;
        }
    }

    // 4. Substring match on description
    for (auto& s : steps) {
        if (to_lower_string(s.description).find(q_str) != std::string::npos) {
            return &s;
        }
    }

    return nullptr;
}

const LedgerStep* TaskLedger::find_step(std::string_view query) const {
    return const_cast<TaskLedger*>(this)->find_step(query);
}

bool TaskLedger::mark_step(std::string_view query, LedgerStepStatus new_status, std::string_view note) {
    LedgerStep* target = find_step(query);
    if (!target) return false;
    target->status = new_status;
    if (!note.empty()) {
        target->note = std::string(note);
    }
    return true;
}

void TaskLedger::add_step(std::string description, std::string id) {
    if (description.empty()) return;
    if (id.empty()) {
        id = "step_" + std::to_string(steps.size() + 1);
    }
    // Check if ID already exists
    for (const auto& s : steps) {
        if (s.id == id) {
            id += "_" + std::to_string(steps.size() + 1);
            break;
        }
    }
    steps.push_back(LedgerStep{std::move(id), std::move(description), LedgerStepStatus::pending, {}});
}

std::string TaskLedger::render_markdown() const {
    std::ostringstream ss;
    ss << "# 📋 ACTIVE TASK LEDGER\n";
    if (!objective.empty()) {
        ss << "**Objective:** " << objective << "\n";
    }
    if (!current_status.empty()) {
        ss << "**Current Status:** " << current_status << "\n";
    }

    if (!steps.empty()) {
        ss << "\n### 🎯 Milestones & Action Items:\n";
        for (std::size_t i = 0; i < steps.size(); ++i) {
            const auto& s = steps[i];
            ss << "- " << to_checkbox(s.status) << " Step " << (i + 1)
               << " (" << s.id << "): " << s.description;
            if (s.status == LedgerStepStatus::in_progress) {
                ss << " ◀ [ACTIVE FOCUS]";
            }
            ss << "\n";
            if (!s.note.empty()) {
                ss << "      ↳ Proof/Note: " << s.note << "\n";
            }
        }
    }

    if (!key_findings.empty() || !blockers.empty()) {
        ss << "\n### 🧠 Working Memory & Notes:\n";
        for (const auto& f : key_findings) {
            ss << "- [Finding] " << f << "\n";
        }
        for (const auto& b : blockers) {
            ss << "- [Blocker] " << b << "\n";
        }
    }

    return ss.str();
}

void to_json(Json& j, const LedgerStep& v) {
    j = Json::object();
    j["id"] = v.id;
    j["description"] = v.description;
    j["status"] = to_string(v.status);
    if (!v.note.empty()) {
        j["note"] = v.note;
    }
}

void from_json(const Json& j, LedgerStep& v, const std::string& path) {
    expect_object(j, path);
    v.id = read_string(require(j, path, "id"), path + "/id");
    v.description = read_string(require(j, path, "description"), path + "/description");
    v.status = parse_ledger_status(read_string(require(j, path, "status"), path + "/status"));
    v.note = j.value("note", std::string{});
}

void to_json(Json& j, const TaskLedger& v) {
    j = Json::object();
    j["task_id"] = v.task_id;
    j["objective"] = v.objective;
    j["current_status"] = v.current_status;
    j["last_updated_turn"] = v.last_updated_turn;
    Json steps_arr = Json::array();
    for (const auto& s : v.steps) {
        Json sj;
        to_json(sj, s);
        steps_arr.push_back(std::move(sj));
    }
    j["steps"] = std::move(steps_arr);
    j["key_findings"] = v.key_findings;
    j["blockers"] = v.blockers;
}

void from_json(const Json& j, TaskLedger& v, const std::string& path) {
    expect_object(j, path);
    v.task_id = j.value("task_id", std::string{});
    v.objective = j.value("objective", std::string{});
    v.current_status = j.value("current_status", std::string{});
    v.last_updated_turn = j.value("last_updated_turn", 0ULL);
    v.steps.clear();
    if (j.contains("steps") && j["steps"].is_array()) {
        for (std::size_t i = 0; i < j["steps"].size(); ++i) {
            LedgerStep s;
            from_json(j["steps"][i], s, path + "/steps[" + std::to_string(i) + "]");
            v.steps.push_back(std::move(s));
        }
    }
    v.key_findings = j.value("key_findings", std::vector<std::string>{});
    v.blockers = j.value("blockers", std::vector<std::string>{});
}

}  // namespace aquila

