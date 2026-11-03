"""TDD tests for code-mode run diagnostics."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.code_run_diagnostics import (
    analyze_jsonl,
    check_habit_tracker_project,
    detect_stall_signals,
    diagnose_code_run,
    format_diagnostic_report,
)


def test_detect_stall_signals_create_file_loop():
    caps = ["cap.dev.create_file@v1"] * 4 + ["cap.dev.recon@v1"]
    signals = detect_stall_signals(caps, ["cap.dev.create_file@v1: exists"])
    kinds = {s.kind for s in signals}
    assert "create_file_loop" in kinds
    assert "repeat_capability" in kinds


def test_detect_stall_signals_exists_block_loop():
    failures = ["OS BLOCK: exists", "OS BLOCK: exists again"]
    signals = detect_stall_signals([], failures)
    assert any(s.kind == "exists_block_loop" for s in signals)


def test_check_habit_tracker_project_passes(tmp_path):
    state = {
        "root": str(tmp_path / "proj"),
        "files": [
            {
                "path": "habit.py",
                "content": (
                    "import json\n"
                    "def main():\n"
                    "    if cmd == 'add': pass\n"
                    "    if cmd == 'done': pass\n"
                    "    if cmd == 'list': pass\n"
                    "DATA = 'habits.json'\n"
                ),
            },
            {
                "path": "tests/test_habit.py",
                "content": "def test_add():\n    assert True\n",
            },
            {"path": "README.md", "content": "# Habit tracker\n"},
        ],
    }
    ok, fails = check_habit_tracker_project(state=state)
    assert ok, fails


def test_check_habit_tracker_project_missing_files():
    ok, fails = check_habit_tracker_project(state={"files": []})
    assert not ok
    assert any("habit.py" in f for f in fails)


def test_analyze_jsonl_fixture(tmp_path):
    log = tmp_path / "run.jsonl"
    rows = [
        {"event": "session_start", "task": "t1"},
        {"event": "llm_response", "duration_ms": 1000},
        {"event": "tool_start", "cap_id": "cap.dev.create_file@v1"},
        {"event": "run_state_checkpoint", "cap_id": "cap.dev.create_file@v1", "ok": False},
        {"event": "forced_advance", "reason": "iteration_limit"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    parsed = analyze_jsonl(log)
    assert parsed["llm_turns"] == 1
    assert parsed["forced_advances"] == 1
    assert "cap.dev.create_file@v1" in parsed["capability_calls"]


def test_diagnose_code_run_no_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    diag = diagnose_code_run("missing_task")
    report = format_diagnostic_report(diag)
    assert "missing_task" in report
    assert diag.jsonl_path is None
