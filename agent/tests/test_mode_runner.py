import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    ModeResult,
    delegation_dir,
    load_delegation_stack,
    make_delegation_task_name,
    resolve_nested_task_file,
)


def test_mode_result_roundtrip():
    mr = ModeResult(
        status="completed",
        mode="research",
        summary="done",
        deliverable_path="/tmp/x.md",
        ledger_path="/tmp/x.json",
        metrics={"wall_time_s": 1.2},
        delegation_id="research_1",
    )
    data = mr.to_dict()
    back = ModeResult.from_dict(data)
    assert back.mode == "research"
    assert back.metrics["wall_time_s"] == 1.2


def test_resolve_nested_task_file(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    plan_dir, task_file = resolve_nested_task_file(
        mode="research",
        task_name="research_123",
        parent_task_id="parent_task",
    )
    assert "delegations" in task_file
    assert Path(task_file).parent.exists()


def test_load_delegation_stack_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    assert load_delegation_stack("missing") == []


def test_make_delegation_task_name():
    name = make_delegation_task_name("parent", "code")
    assert name.startswith("code_")
