#include "aquila/types/task_ledger.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

using namespace aquila;

TEST_CASE("TaskLedger: status enum, checkboxes, and string conversions", "[ledger]") {
    CHECK(to_string(LedgerStepStatus::pending) == "pending");
    CHECK(to_string(LedgerStepStatus::in_progress) == "in_progress");
    CHECK(to_string(LedgerStepStatus::completed) == "completed");
    CHECK(to_string(LedgerStepStatus::blocked) == "blocked");
    CHECK(to_string(LedgerStepStatus::skipped) == "skipped");

    CHECK(to_checkbox(LedgerStepStatus::pending) == "[ ]");
    CHECK(to_checkbox(LedgerStepStatus::in_progress) == "[/]");
    CHECK(to_checkbox(LedgerStepStatus::completed) == "[x]");
    CHECK(to_checkbox(LedgerStepStatus::blocked) == "[!]");
    CHECK(to_checkbox(LedgerStepStatus::skipped) == "[-]");

    CHECK(parse_ledger_status("completed") == LedgerStepStatus::completed);
    CHECK(parse_ledger_status("done") == LedgerStepStatus::completed);
    CHECK(parse_ledger_status("[x]") == LedgerStepStatus::completed);
    CHECK(parse_ledger_status("in_progress") == LedgerStepStatus::in_progress);
    CHECK(parse_ledger_status("active") == LedgerStepStatus::in_progress);
    CHECK(parse_ledger_status("[/]") == LedgerStepStatus::in_progress);
    CHECK(parse_ledger_status("blocked") == LedgerStepStatus::blocked);
    CHECK(parse_ledger_status("failed") == LedgerStepStatus::blocked);
    CHECK(parse_ledger_status("[!]") == LedgerStepStatus::blocked);
    CHECK(parse_ledger_status("skipped") == LedgerStepStatus::skipped);
    CHECK(parse_ledger_status("[-]") == LedgerStepStatus::skipped);
    CHECK(parse_ledger_status("unknown_status") == LedgerStepStatus::pending);
}

TEST_CASE("TaskLedger: tolerant step lookup by index, id, and keyword", "[ledger]") {
    TaskLedger ledger;
    ledger.task_id = "test_task";
    ledger.objective = "Verify system integrity";
    ledger.current_status = "Initializing";

    ledger.add_step("Create virtual environment in workspace", "setup_env");
    ledger.add_step("Install dependencies via pip", "install_deps");
    ledger.add_step("Execute test suite", "run_tests");
    ledger.add_step("Verify implementation quality", "verify_quality");

    REQUIRE(ledger.steps.size() == 4);

    // 1. Lookup by 1-based index (integer string)
    LedgerStep* s1 = ledger.find_step("1");
    REQUIRE(s1 != nullptr);
    CHECK(s1->id == "setup_env");

    LedgerStep* s3 = ledger.find_step("3");
    REQUIRE(s3 != nullptr);
    CHECK(s3->id == "run_tests");

    // Out of range returns nullptr
    CHECK(ledger.find_step("0") == nullptr);
    CHECK(ledger.find_step("5") == nullptr);

    // 2. Lookup by "step_N" prefix
    LedgerStep* s2 = ledger.find_step("step_2");
    REQUIRE(s2 != nullptr);
    CHECK(s2->id == "install_deps");

    // 3. Lookup by exact ID (case-insensitive)
    LedgerStep* s4 = ledger.find_step("VERIFY_QUALITY");
    REQUIRE(s4 != nullptr);
    CHECK(s4->id == "verify_quality");

    // 4. Lookup by description substring
    LedgerStep* s_deps = ledger.find_step("dependencies");
    REQUIRE(s_deps != nullptr);
    CHECK(s_deps->id == "install_deps");

    LedgerStep* s_suite = ledger.find_step("test suite");
    REQUIRE(s_suite != nullptr);
    CHECK(s_suite->id == "run_tests");
}

TEST_CASE("TaskLedger: step marking and completion invariants", "[ledger]") {
    TaskLedger ledger;
    ledger.add_step("Step Alpha", "alpha");
    ledger.add_step("Step Beta", "beta");
    ledger.add_step("Step Gamma", "gamma");

    CHECK_FALSE(ledger.all_mandatory_completed());
    CHECK(ledger.incomplete_steps().size() == 3);

    // Mark step 1 in_progress
    CHECK(ledger.mark_step("alpha", LedgerStepStatus::in_progress));
    CHECK_FALSE(ledger.all_mandatory_completed());

    // Mark step 1 completed with note
    CHECK(ledger.mark_step("1", LedgerStepStatus::completed, "Alpha finished cleanly"));
    CHECK(ledger.find_step("alpha")->status == LedgerStepStatus::completed);
    CHECK(ledger.find_step("alpha")->note == "Alpha finished cleanly");
    CHECK_FALSE(ledger.all_mandatory_completed());
    CHECK(ledger.incomplete_steps().size() == 2);

    // Mark step 2 completed
    CHECK(ledger.mark_step("step_2", LedgerStepStatus::completed));
    CHECK_FALSE(ledger.all_mandatory_completed());

    // Mark step 3 skipped
    CHECK(ledger.mark_step("gamma", LedgerStepStatus::skipped, "Optional step bypassed"));
    CHECK(ledger.all_mandatory_completed());
    CHECK(ledger.incomplete_steps().empty());
}

TEST_CASE("TaskLedger: Markdown rendering contains checkboxes, active focus, and working memory", "[ledger]") {
    TaskLedger ledger;
    ledger.task_id = "test_render";
    ledger.objective = "Implement ping utility";
    ledger.current_status = "Running zero-arg execution test";
    ledger.add_step("Create ping_health.py", "create");
    ledger.add_step("Run python execution check", "execute");
    ledger.add_step("Complete recipe", "complete");

    ledger.mark_step("1", LedgerStepStatus::completed, "Created with DNS and TCP checks");
    ledger.mark_step("2", LedgerStepStatus::in_progress);
    ledger.key_findings.push_back("Raw ICMP sockets require administrator privileges");
    ledger.blockers.push_back("Need fallback to TCP port 80");

    const std::string md = ledger.render_markdown();

    CHECK(md.find("# 📋 ACTIVE TASK LEDGER") != std::string::npos);
    CHECK(md.find("**Objective:** Implement ping utility") != std::string::npos);
    CHECK(md.find("**Current Status:** Running zero-arg execution test") != std::string::npos);
    CHECK(md.find("- [x] Step 1 (create): Create ping_health.py") != std::string::npos);
    CHECK(md.find("↳ Proof/Note: Created with DNS and TCP checks") != std::string::npos);
    CHECK(md.find("- [/] Step 2 (execute): Run python execution check ◀ [ACTIVE FOCUS]") != std::string::npos);
    CHECK(md.find("- [ ] Step 3 (complete): Complete recipe") != std::string::npos);
    CHECK(md.find("[Finding] Raw ICMP sockets require administrator privileges") != std::string::npos);
    CHECK(md.find("[Blocker] Need fallback to TCP port 80") != std::string::npos);
}

TEST_CASE("TaskLedger: JSON roundtrip serialization", "[ledger]") {
    TaskLedger original;
    original.task_id = "ledger_42";
    original.objective = "Build persona Ada";
    original.current_status = "Writing lore facts";
    original.last_updated_turn = 5;
    original.add_step("Initialize persona record", "init");
    original.add_step("Write initialization prompt", "prompt");
    original.mark_step("init", LedgerStepStatus::completed, "Saved persona.json");
    original.mark_step("prompt", LedgerStepStatus::in_progress);
    original.key_findings = {"Mentor voice calibrated", "Depth gate satisfied"};
    original.blockers = {};

    Json serialized;
    to_json(serialized, original);

    TaskLedger restored;
    from_json(serialized, restored, "/ledger");

    CHECK(restored.task_id == original.task_id);
    CHECK(restored.objective == original.objective);
    CHECK(restored.current_status == original.current_status);
    CHECK(restored.last_updated_turn == original.last_updated_turn);
    CHECK(restored.steps == original.steps);
    CHECK(restored.key_findings == original.key_findings);
    CHECK(restored.blockers == original.blockers);
}

