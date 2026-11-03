"""Contract tests: code mode evaluate_run honors session metrics over scorecard theater."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core.capability_harness import evaluate_run


def _smoke_report(
    tmp_path: Path,
    *,
    synced: bool,
    scorecard_failures: list[str] | None = None,
    with_file: bool = True,
) -> dict:
    if with_file:
        smoke = tmp_path / "Agent-Code" / "harness-smoke" / "harness_smoke.py"
        smoke.parent.mkdir(parents=True, exist_ok=True)
        smoke.write_text("print('HARNESS_OK')\n", encoding="utf-8")

    logs = tmp_path / "Agent-Logs"
    logs.mkdir(parents=True, exist_ok=True)
    task = "code_smoke_contract"
    jsonl = logs / f"{task}_20260101_120000.jsonl"
    jsonl.write_text(
        json.dumps({"event": "session_start", "task": task, "mode": "code"}) + "\n",
        encoding="utf-8",
    )

    return {
        "scenario_id": "code_smoke_file",
        "mode": "code",
        "task_name": task,
        "jsonl_path": str(jsonl),
        "run_status": "completed",
        "scorecard_passed": False,
        "scorecard_failures": scorecard_failures
        or ["finish_task / finalize capability not observed in log"],
        "code_session_metrics": {
            "synced": synced,
            "turns": 3,
            "wall_s": 7.3,
            "parse_failures": 0,
        },
        "mode_result": {
            "status": "completed",
            "metrics": {
                "code_session": {
                    "synced": synced,
                    "turns": 3,
                    "wall_s": 7.3,
                }
            },
        },
    }


def test_evaluate_passes_when_synced_despite_finish_scorecard(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    report = _smoke_report(tmp_path, synced=True)
    passed, failures = evaluate_run(report)
    assert passed is True
    assert failures == []


def test_evaluate_fails_when_not_synced_and_no_acceptance_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    report = _smoke_report(tmp_path, synced=False, with_file=False)
    passed, failures = evaluate_run(report)
    assert passed is False
    assert any("expected file missing" in f for f in failures)


def test_evaluate_fails_habit_when_files_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    logs = tmp_path / "Agent-Logs"
    logs.mkdir(parents=True, exist_ok=True)
    task = "code_habit_contract"
    jsonl = logs / f"{task}_20260101_120000.jsonl"
    jsonl.write_text(
        json.dumps({"event": "session_start", "task": task, "mode": "code"}) + "\n",
        encoding="utf-8",
    )
    state = tmp_path / "Agent-Code" / "active_code_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"root": str(tmp_path / "Agent-Code" / "habit-project"), "files": []}),
        encoding="utf-8",
    )

    report = {
        "scenario_id": "code_habit_tracker",
        "mode": "code",
        "task_name": task,
        "jsonl_path": str(jsonl),
        "run_status": "completed",
        "scorecard_passed": True,
        "scorecard_failures": [],
        "code_session_metrics": {
            "synced": False,
            "turns": 16,
            "wall_s": 373.0,
        },
        "mode_result": {"status": "completed"},
    }
    passed, failures = evaluate_run(report)
    assert passed is False
    assert any("habit_tracker" in f or "synced file missing" in f for f in failures)


def test_evaluate_keeps_real_scorecard_failures_when_synced(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    report = _smoke_report(
        tmp_path,
        synced=True,
        scorecard_failures=[
            "finish_task / finalize capability not observed in log",
            "parse_failures 3 > 0",
        ],
    )
    passed, failures = evaluate_run(report)
    assert passed is False
    assert any("parse_failures" in f for f in failures)
    assert not any("finish_task" in f for f in failures)


def test_evaluate_passes_when_completed_without_synced(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    report = _smoke_report(tmp_path, synced=False)
    report["code_session_metrics"]["synced"] = False
    report["code_session_metrics"]["completed"] = True
    passed, failures = evaluate_run(report)
    assert passed is True
    assert failures == []


def test_evaluate_passes_disk_acceptance_despite_failed_status(tmp_path, monkeypatch):
    """Smoke: file on disk counts even if model hit turn limit without final_report."""
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    report = _smoke_report(tmp_path, synced=False)
    report["run_status"] = "failed"
    report["mode_result"]["status"] = "failed"
    report["code_session_metrics"]["synced"] = False
    report["code_session_metrics"]["completed"] = False
    passed, failures = evaluate_run(report)
    assert passed is True
    assert failures == []
