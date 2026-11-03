"""Checkpoint and code adapter tests for RunState."""
from __future__ import annotations

import json

from agent.capabilities.base import CapabilityResult
from agent.core.implementation_plan import infer_completed_items
from agent.core.loop_objectives import MilestoneState, apply_ground_truth_to_milestone_state
from agent.core.run_state_providers import CodeGroundTruthProvider
from agent.core.task_artifacts import write_plan_artifact


def test_infer_completed_items_code_create_test(tmp_agent_dirs):
    result = CapabilityResult.success(file_path="tests/test_habit.py")
    ticks = infer_completed_items(
        "cap.dev.create_file@v1",
        result,
        {},
        mode="code",
    )
    assert "tests-1" in ticks


def test_code_ground_truth_provider_snapshot(tmp_agent_dirs, monkeypatch):
    from agent.storage import agent_data_path

    code_dir = agent_data_path("Agent-Code")
    code_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "project_id": "habit",
        "root": str(code_dir / "habit"),
        "files": {"tests/test_habit.py": {"content": "def test_x(): pass"}},
    }
    (code_dir / "active_code_state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    provider = CodeGroundTruthProvider()
    snap = provider.snapshot(task_id="t", mode="code")
    assert snap["setup_done"]
    assert "tests/test_habit.py" in snap["buffer_files"]


def test_code_ground_truth_provider_snapshot_list_files(tmp_agent_dirs):
    from agent.storage import agent_data_path

    code_dir = agent_data_path("Agent-Code")
    code_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "project_id": "habit",
        "root": str(code_dir / "habit"),
        "files": [
            {"path": "habits.json", "content": "{}", "line_count": 1},
            {"path": "tests/test_habit.py", "content": "def test_x(): pass", "line_count": 1},
        ],
    }
    (code_dir / "active_code_state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    provider = CodeGroundTruthProvider()
    snap = provider.snapshot(task_id="t", mode="code")
    assert snap["file_count"] == 2
    assert "habits.json" in snap["buffer_files"]
    assert "tests/test_habit.py" in snap["buffer_files"]


def test_apply_ground_truth_does_not_mark_implement_on_test_only(tmp_agent_dirs):
    st = MilestoneState()
    apply_ground_truth_to_milestone_state(
        st,
        "code",
        {"buffer_files": ["tests/test_habit.py"], "setup_done": True},
    )
    assert not st.file_edited

    apply_ground_truth_to_milestone_state(
        st,
        "code",
        {"buffer_files": ["tests/test_habit.py", "habit.py"], "setup_done": True},
    )
    assert st.file_edited


def test_habit_tracker_regression_sequence(tmp_agent_dirs):
    """After create_file on test, checklist ticks and ground truth reflect file."""
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "user_goal": "CLI habit tracker",
        "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        "implementation": {
            "checklist": [
                {"id": "setup-1", "text": "Setup", "status": "pending"},
                {"id": "tests-1", "text": "Tests", "status": "pending"},
            ],
        },
    }
    write_plan_artifact("habit-reg", "code", plan)

    from agent.core.run_state import TaskRunContext
    from agent.policies.context_budget import resolve_context_profile

    ctx = TaskRunContext.bootstrap(task_id="habit-reg", mode="code", goal="CLI habit tracker")
    result = CapabilityResult.success(
        summary="wrote test",
        file_path="tests/test_habit.py",
    )
    ctx.checkpoint_capability(
        cap_id="cap.dev.create_file@v1",
        result=result,
        summary_text="Capability 'cap.dev.create_file@v1' result:\nCreated tests/test_habit.py",
        client=None,
        profile=resolve_context_profile(num_ctx_override=32768),
    )
    prompt = ctx.render_for_prompt()
    assert "tests-1" in prompt or "Tests" in prompt or "test_habit" in prompt.lower()
    done = [c for c in ctx.checklist if c.status == "done"]
    assert any(c.id == "tests-1" for c in done)


def test_create_file_result_file_path_ticks_tests(tmp_agent_dirs):
    from agent.capabilities.base import CapabilityResult
    from agent.core.run_state import TaskRunContext
    from agent.policies.context_budget import resolve_context_profile
    from agent.core.task_artifacts import write_plan_artifact

    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "user_goal": "CLI habit tracker",
        "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        "implementation": {
            "checklist": [
                {"id": "tests-1", "text": "Tests", "status": "pending"},
            ],
        },
    }
    write_plan_artifact("fp-tick", "code", plan)
    ctx = TaskRunContext.bootstrap(task_id="fp-tick", mode="code", goal="CLI habit tracker")
    result = CapabilityResult.success(
        summary="created",
        file_path="tests/test_habit.py",
        tool_result="ok",
    )
    ctx.checkpoint_capability(
        cap_id="cap.dev.create_file@v1",
        result=result,
        summary_text="Created tests/test_habit.py",
        client=None,
        profile=resolve_context_profile(num_ctx_override=32768),
    )
    done = [c for c in ctx.checklist if c.status == "done"]
    assert any(c.id == "tests-1" for c in done)


def test_snapshot_sync_ticks_tests_from_buffer(tmp_agent_dirs):
    from agent.core.run_state import TaskRunContext
    from agent.core.run_state_providers import CodeGroundTruthProvider
    from agent.core.task_artifacts import write_plan_artifact
    from agent.policies.context_budget import resolve_context_profile

    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "user_goal": "CLI habit tracker",
        "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        "implementation": {
            "checklist": [
                {"id": "tests-1", "text": "Tests", "status": "pending"},
            ],
        },
    }
    write_plan_artifact("snap-tick", "code", plan)
    ctx = TaskRunContext.bootstrap(task_id="snap-tick", mode="code", goal="CLI habit tracker")
    provider = CodeGroundTruthProvider()
    snapshot = {
        "buffer_files": ["tests/test_habit.py"],
        "setup_done": True,
        "tests_pass": None,
    }
    ticks = provider.infer_checklist_ticks_from_snapshot(snapshot)
    assert "tests-1" in ticks
    ctx.ground_truth = snapshot
    ctx._sync_checklist_to_plan(ticks)
    done = [c for c in ctx.checklist if c.status == "done"]
    assert any(c.id == "tests-1" for c in done)
