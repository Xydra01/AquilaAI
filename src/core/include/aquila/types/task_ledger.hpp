#pragma once

#include "aquila/json.hpp"

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace aquila {

// State of an individual milestone / step in the Task Ledger.
enum class LedgerStepStatus {
    pending,      // [ ] Not started yet
    in_progress,  // [/] Currently active focus
    completed,    // [x] Finished and verified
    blocked,      // [!] Blocked by error, dependency, or issue
    skipped       // [-] Explicitly bypassed or no longer needed
};

[[nodiscard]] std::string_view to_string(LedgerStepStatus status) noexcept;
[[nodiscard]] std::string_view to_checkbox(LedgerStepStatus status) noexcept;
[[nodiscard]] LedgerStepStatus parse_ledger_status(std::string_view text);

struct LedgerStep {
    std::string id;            // Short identifier, e.g. "step_1", "setup", "verify"
    std::string description;   // Clear, actionable instruction
    LedgerStepStatus status = LedgerStepStatus::pending;
    std::string note;          // Optional verification proof or outcome details

    bool operator==(const LedgerStep&) const = default;
};

// Strongly-typed Task Ledger: maintains procedural progress across long horizons.
// Rendered into the Anchored Block of ContextCondenser so it is visible on every
// turn and preserved across End-of-Context Compaction (EOCC).
struct TaskLedger {
    std::string task_id;
    std::string objective;
    std::string current_status;  // High-level progress summary / active focus
    std::vector<LedgerStep> steps;
    std::vector<std::string> key_findings;
    std::vector<std::string> blockers;
    std::uint64_t last_updated_turn = 0;

    bool operator==(const TaskLedger&) const = default;

    // Returns true iff all steps are in completed or skipped state.
    [[nodiscard]] bool all_mandatory_completed() const noexcept;

    // Returns descriptions or IDs of all steps still in pending or in_progress state.
    [[nodiscard]] std::vector<std::string> incomplete_steps() const;

    // Tolerant step lookup: matches by exact id, 1-based index (e.g. "1" or "step_1"),
    // or case-insensitive description substring.
    [[nodiscard]] LedgerStep* find_step(std::string_view query);
    [[nodiscard]] const LedgerStep* find_step(std::string_view query) const;

    // Marks a step with a new status and optional note. Returns true if found and updated.
    bool mark_step(std::string_view query, LedgerStepStatus new_status, std::string_view note = {});

    // Appends a new step if it does not already exist.
    void add_step(std::string description, std::string id = {});

    // High-contrast, human- and LLM-friendly Markdown rendering for active working context.
    [[nodiscard]] std::string render_markdown() const;
};

void to_json(Json& j, const LedgerStep& v);
void from_json(const Json& j, LedgerStep& v, const std::string& path);

void to_json(Json& j, const TaskLedger& v);
void from_json(const Json& j, TaskLedger& v, const std::string& path);

}  // namespace aquila

