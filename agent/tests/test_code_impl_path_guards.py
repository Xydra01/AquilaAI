"""Guards for code path helpers (Phase 3: LoopEngine FSM tests removed)."""
from __future__ import annotations

from agent.capabilities.base import CapabilityResult
from agent.core.implementation_plan import (
    infer_completed_items,
    is_code_impl_source_path,
    is_code_test_path,
)
from agent.core.code_run_diagnostics import check_habit_tracker_project
from agent.core.plan_validator import expand_tdd_code_plan, should_expand_tdd_code_plan


def test_is_code_impl_source_path_rejects_json_and_tests():
    assert is_code_impl_source_path("habit.py")
    assert not is_code_impl_source_path("habits.json")
    assert not is_code_impl_source_path("tests/test_habit.py")
    assert is_code_test_path("tests/test_habit.py")


def test_infer_completed_items_json_does_not_tick_impl():
    ticks = infer_completed_items(
        "cap.dev.create_file@v1",
        CapabilityResult.success(file_path="habits.json"),
        {},
        mode="code",
    )
    assert "impl-1" not in ticks
    assert "tests-1" not in ticks


def test_infer_completed_items_habit_py_ticks_impl():
    ticks = infer_completed_items(
        "cap.dev.create_file@v1",
        CapabilityResult.success(file_path="habit.py"),
        {},
        mode="code",
    )
    assert "impl-1" in ticks or any("impl" in t for t in ticks)


def test_should_expand_tdd_code_plan_helpers():
    # Helpers may still exist for archived plan JSON; not used by live code loop.
    assert callable(should_expand_tdd_code_plan)
    assert callable(expand_tdd_code_plan)
    assert callable(check_habit_tracker_project)
