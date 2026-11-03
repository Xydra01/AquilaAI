"""Tests for habit-tracker scaffold healing."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.code_scaffolds import (
    dispatch_scaffold_files,
    heal_habit_tracker_create_file,
    habit_tracker_work_complete,
    is_habit_tracker_goal,
    next_habit_tracker_file,
    scaffold_dispatch_should_run,
    scaffold_for_path,
)


GOAL = (
    "Build a tiny CLI habit tracker: habit.py with add / done / list, "
    "tests/test_habit.py, README.md"
)


def test_is_habit_tracker_goal():
    assert is_habit_tracker_goal(GOAL)
    assert not is_habit_tracker_goal("build a web app")


def test_next_file_prefers_tests_then_impl_then_readme():
    assert next_habit_tracker_file(buffer_paths=[]) == "tests/test_habit.py"
    assert next_habit_tracker_file(buffer_paths=["tests/test_habit.py"]) == "habit.py"
    assert (
        next_habit_tracker_file(buffer_paths=["tests/test_habit.py", "habit.py"])
        == "README.md"
    )


def test_scaffold_content_has_required_hints():
    impl = scaffold_for_path("habit.py")
    assert impl
    assert "add" in impl.lower()
    assert "done" in impl.lower()
    assert "list" in impl.lower()
    assert "habits.json" in impl.lower()
    tests = scaffold_for_path("tests/test_habit.py")
    assert tests and "def test" in tests
    readme = scaffold_for_path("README.md")
    assert readme and "habit.py" in readme


def test_heal_empty_create_file_under_harness(monkeypatch):
    monkeypatch.setenv("AQUILA_HARNESS_FORCE_MICRO_PLAN", "1")
    monkeypatch.setenv("AQUILA_SCAFFOLD_DISPATCH", "1")
    healed = heal_habit_tracker_create_file(
        goal=GOAL, args={}, step_kind="work", buffer_paths=[]
    )
    assert healed
    assert healed["file_path"] == "tests/test_habit.py"
    assert "def test" in healed["content"]


def test_heal_impl_after_tests_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_HARNESS_FORCE_MICRO_PLAN", "1")
    monkeypatch.setenv("AQUILA_SCAFFOLD_DISPATCH", "1")
    import json

    from agent.storage import agent_data_path

    code_dir = agent_data_path("Agent-Code")
    code_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "project_id": "habit",
        "root": str(code_dir / "habit"),
        "files": [{"path": "tests/test_habit.py", "content": "def test_x(): pass"}],
    }
    (code_dir / "active_code_state.json").write_text(json.dumps(state), encoding="utf-8")
    healed = heal_habit_tracker_create_file(goal=GOAL, args={}, step_kind="work")
    assert healed
    assert healed["file_path"] == "habit.py"
    assert "argparse" in healed["content"]


def test_habit_tracker_work_complete():
    paths = ["tests/test_habit.py", "habit.py", "README.md"]
    assert habit_tracker_work_complete(buffer_paths=paths)
    assert not habit_tracker_work_complete(buffer_paths=["habit.py"])


def test_dispatch_scaffold_writes_all_files(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_SCAFFOLD_DISPATCH", "1")
    import json

    from agent.storage import agent_data_path

    code_dir = agent_data_path("Agent-Code")
    code_dir.mkdir(parents=True, exist_ok=True)
    state = {"project_id": "habit", "root": str(code_dir / "habit"), "files": []}
    (code_dir / "active_code_state.json").write_text(json.dumps(state), encoding="utf-8")
    written = dispatch_scaffold_files(GOAL)
    assert len(written) == 3
    assert "tests/test_habit.py" in written
    assert "habit.py" in written
    assert "README.md" in written


def test_scaffold_dispatch_skips_when_buffer_nonempty(monkeypatch):
    monkeypatch.setenv("AQUILA_SCAFFOLD_DISPATCH", "1")
    monkeypatch.setattr(
        "agent.core.code_scaffolds._buffer_paths",
        lambda: ["habit.py"],
    )
    assert not scaffold_dispatch_should_run(GOAL)
