import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    HARNESS_SCENARIOS,
    build_run_report,
    clear_harness_stale_state,
    evaluate_run,
    list_scenarios,
)


def test_list_scenarios_filters_mode():
    code_only = list_scenarios(mode="code")
    assert code_only
    assert all(s["mode"] == "code" for s in code_only)


def test_build_and_evaluate_fixture_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    logs = tmp_path / "Agent-Logs"
    logs.mkdir(parents=True)
    task = "harness_test_task"
    jsonl = logs / f"{task}_20260101_120000.jsonl"
    lines = [
        {"ts": "2026-01-01T12:00:00", "event": "session_start", "task": task, "mode": "code"},
        {
            "ts": "2026-01-01T12:00:05",
            "event": "llm_response",
            "duration_ms": 2000,
            "body": "x" * 200,
            "output_tokens_per_s": 25.0,
            "output_tokens_est": 50,
        },
        {"ts": "2026-01-01T12:00:06", "event": "tool_end", "tool_name": "read_file"},
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")

    report = build_run_report(
        scenario_id="code_local_read",
        engine="stock",
        task_name=task,
        mode_result={
            "status": "completed",
            "deliverable_path": str(tmp_path / "Agent-Creations" / f"{task}.md"),
            "summary": "done",
        },
    )
    (tmp_path / "Agent-Creations").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Agent-Creations" / f"{task}.md").write_text("y" * 150, encoding="utf-8")

    passed, failures = evaluate_run(report)
    assert report.get("median_output_tokens_per_s") == 25.0 or report.get("tool_calls") == 1
    assert passed or "scorecard" not in str(failures)


def test_clear_harness_stale_state_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    out = clear_harness_stale_state()
    assert out.get("ok") is True


def test_harness_scenario_registry_covers_modes():
    modes = {HARNESS_SCENARIOS[k]["mode"] for k in HARNESS_SCENARIOS}
    assert len(HARNESS_SCENARIOS) >= 6
    assert "code" in modes
    assert "research" in modes
    assert "writing" in modes
    assert "task" in modes


def test_force_micro_plan_scenarios():
    assert HARNESS_SCENARIOS["code_smoke_file"].get("force_micro_plan") is True


def test_check_acceptance_file_glob(tmp_path, monkeypatch):
    from agent.core import _check_acceptance

    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    sub = tmp_path / "Agent-Code" / "harness-smoke"
    sub.mkdir(parents=True)
    (sub / "harness_smoke.py").write_text("print('HARNESS_OK')\n", encoding="utf-8")
    failures = _check_acceptance(
        {"acceptance": {"check_file_glob": "**/harness_smoke.py", "file_contains": "HARNESS_OK"}},
        task_name="t",
        mode="code",
        mode_result=None,
    )
    assert failures == []
