"""Parity tests for capability-only code mode."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skip(
    reason="Phase 3: code mode uses code_agent, not LoopEngine capability act"
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities import get_capability, run_capability
from agent.capabilities.adapters import (
    CODE_STEP_ALLOWLIST,
    allowed_capabilities_for_step,
)
from agent.capabilities.base import CapabilityContext
from agent.core import LoopEngine
from agent.core.fast_path import _step_for_mode
from agent.core.loop_objectives import build_milestones_from_plan_steps
from agent.core.plan_validator import (
    expand_dynamic_code_plan,
    validate_and_tune_plan,
)
from agent.functions.code import resolve_recipe
from agent.policies import CapabilityCodePolicy, get_step_policy, expand_code_documentation_plan
from agent.storage import DualMemorySystem


@pytest.fixture
def capability_env(monkeypatch):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "0")
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    monkeypatch.setenv("AQUILA_AUTO_ADVANCE_MILESTONES", "1")
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "0")
    monkeypatch.delenv("AQUILA_DEV_RAW_TOOL", raising=False)
    monkeypatch.setattr(
        "agent.storage.preferences.apply_preferences_to_environ",
        lambda *args, **kwargs: None,
    )


def test_code_capabilities_registered():
    for cap_id in (
        "cap.dev.project_setup@v1",
        "cap.dev.recon@v1",
        "cap.dev.read_region@v1",
        "cap.dev.edit_apply@v1",
        "cap.dev.create_file@v1",
        "cap.dev.run_tests@v1",
        "cap.dev.run_linter@v1",
        "cap.dev.sync_project@v1",
        "cap.dev.write_docs@v1",
        "cap.dev.light_coding_context@v1",
        "cap.dev.raw_tool@v1",
        "cap.plan.generate_code@v1",
    ):
        assert get_capability(cap_id) is not None, cap_id


def test_code_recipe_and_plan_attach(capability_env):
    recipe = resolve_recipe(dynamic_loop=True)
    assert recipe.recipe_id == "fn.dev.dynamic_work"
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "implement", "status": "pending", "step_kind": "work"},
            {"description": "done", "status": "pending", "step_kind": "finalize"},
        ],
    }
    tuned, _ = validate_and_tune_plan(plan, "code", "Add a helper function")
    assert tuned.get("capability_recipe") == "fn.dev.dynamic_work"
    for step in tuned["steps"]:
        assert step.get("capability_id"), step


def test_loop_uses_capabilities_not_tools(tmp_agent_dirs, capability_env):
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Code mode.",
        mode="code",
        mode_label="Code",
        plan_dir="Agent-Tasks",
        memory=mem,
        base_tools={"run_pytest": {"func": MagicMock(), "description": "legacy"}},
    )
    assert engine._uses_capability_act() is True
    schema = engine._schema_for_capability_step("work", is_final_step=False)
    props = schema.get("properties") or {}
    assert "capabilities" in props
    assert "tools" not in props
    engine.executor.execute.assert_not_called()


def test_dynamic_work_allowlist_includes_edit_and_test():
    allowed = allowed_capabilities_for_step("work", mode="code")
    assert "cap.dev.edit_apply@v1" in allowed
    assert "cap.dev.run_tests@v1" in allowed
    assert "cap.dev.recon@v1" in allowed
    assert allowed == CODE_STEP_ALLOWLIST["work"]


def test_tdd_step_allowlists():
    red = allowed_capabilities_for_step("tdd_red", mode="code")
    green = allowed_capabilities_for_step("tdd_green", mode="code")
    assert "cap.dev.create_file@v1" in red
    assert "cap.dev.edit_apply@v1" in green
    assert "cap.dev.read_region@v1" in green
    assert "cap.dev.run_tests@v1" in green
    assert "cap.dev.project_setup@v1" not in green


def test_code_policy_blocks_repeat_project_setup():
    policy = CapabilityCodePolicy(mode="code", step_kind="work")
    msg = policy.validate_capability_call(
        "cap.dev.project_setup@v1",
        tools_succeeded={"cap.dev.project_setup@v1"},
    )
    assert msg and "already set up" in msg.lower()


def test_code_policy_blocks_repeat_recon_on_work():
    policy = CapabilityCodePolicy(mode="code", step_kind="work")
    msg = policy.validate_capability_call(
        "cap.dev.recon@v1",
        tools_succeeded={"cap.dev.recon@v1"},
    )
    assert msg and "recon already" in msg.lower()


def test_code_policy_allows_second_recon_on_explore():
    policy = CapabilityCodePolicy(mode="code", step_kind="explore")
    assert (
        policy.validate_capability_call(
            "cap.dev.recon@v1",
            tools_succeeded={"cap.dev.recon@v1"},
        )
        is None
    )


def test_code_policy_blocks_setup_when_active_root_exists(tmp_path, monkeypatch):
    root = tmp_path / "Agent-Code" / "habit-tracker"
    root.mkdir(parents=True)
    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.get_active_project_scope",
        lambda: {
            "project_name": "habit-tracker",
            "root": str(root),
            "workspace_mode": "sandbox",
        },
    )
    policy = CapabilityCodePolicy(mode="code", step_kind="work")
    msg = policy.validate_capability_call("cap.dev.project_setup@v1")
    assert msg and "already active" in msg.lower()


def test_code_policy_allows_setup_when_active_root_missing(tmp_path, monkeypatch):
    missing = tmp_path / "Agent-Code" / "new_project"
    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.get_active_project_scope",
        lambda: {
            "project_name": "new_project",
            "root": str(missing),
            "workspace_mode": "sandbox",
        },
    )
    policy = CapabilityCodePolicy(mode="code", step_kind="work")
    assert policy.validate_capability_call("cap.dev.project_setup@v1") is None


def test_policy_allows_raw_tool_when_env_set(monkeypatch):
    monkeypatch.setenv("AQUILA_DEV_RAW_TOOL", "1")
    policy = CapabilityCodePolicy(mode="code", step_kind="work")
    assert policy.validate_capability_call("cap.dev.raw_tool@v1") is None


def test_doc_expander_attaches_write_docs():
    plan = {
        "steps": [
            {"step_kind": "explore", "description": "a", "max_iterations": 8},
            {"step_kind": "explore", "description": "b", "max_iterations": 8},
            {"step_kind": "explore", "description": "c", "max_iterations": 8},
            {"step_kind": "read", "description": "d", "max_iterations": 5},
            {"step_kind": "read", "description": "e", "max_iterations": 5},
            {"step_kind": "read", "description": "f", "max_iterations": 5},
        ]
    }
    tuned, note = expand_code_documentation_plan(plan, "Write ARCHITECTURE.md")
    assert "Replaced" in note
    code_step = next(s for s in tuned["steps"] if s["step_kind"] == "code")
    assert code_step.get("capability_id") == "cap.dev.write_docs@v1"
    assert tuned["steps"][-1].get("capability_id") == "cap.dev.sync_project@v1"


def test_build_milestones_from_plan_steps_code_only_listed_caps():
    steps = [
        {"step_kind": "explore", "capability_id": "cap.dev.recon@v1"},
        {"step_kind": "work", "capability_id": "cap.dev.edit_apply@v1"},
        {"step_kind": "finalize", "capability_id": "cap.dev.sync_project@v1"},
    ]
    milestones = build_milestones_from_plan_steps(steps, "code", prefix="Capabilities")
    criteria = " ".join(m.get("success_criteria", "") for m in milestones)
    assert "cap.dev.recon@v1" in criteria
    assert "cap.dev.edit_apply@v1" in criteria
    assert "cap.dev.sync_project@v1" in criteria
    assert "finish_task" not in criteria
    assert "run_pytest" not in criteria


def test_micro_plan_finalize_has_no_finish_task(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "0")
    steps = _step_for_mode("code", "Add logging helper")
    blob = " ".join(str(s) for s in steps)
    assert "finish_task" not in blob
    assert any(s.get("capability_id") == "cap.dev.sync_project@v1" for s in steps)


def test_recon_edit_tests_gold_path(tmp_agent_dirs, capability_env, monkeypatch):
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    ctx = CapabilityContext(
        memory=mem,
        task_id="code_gold",
        mode="code",
        user_request="Add helper",
    )
    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.read_code_outline",
        lambda: "Project: demo\nfiles: main.py",
    )
    monkeypatch.setattr(
        "agent.core.tools.get_directory_tree",
        lambda path=".": f"Directory tree for: {path}\n└── main.py",
    )
    recon = run_capability("cap.dev.recon@v1", ctx, {})
    assert recon.ok, recon.error_message

    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.replace_lines",
        lambda *a, **k: "✅ Replaced lines in main.py",
    )
    edit = run_capability(
        "cap.dev.edit_apply@v1",
        ctx,
        {
            "action": "replace_lines",
            "file_path": "main.py",
            "start_line": 1,
            "end_line": 1,
            "new_content": "x = 1\n",
        },
    )
    assert edit.ok, edit.error_message

    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.run_pytest",
        lambda target="": "✅ pytest: 1 passed, 0 failed",
    )
    tests = run_capability("cap.dev.run_tests@v1", ctx, {})
    assert tests.ok, tests.error_message
    assert tests.data.get("tests_green") is True


def test_light_coding_capability(tmp_path, capability_env):
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    ctx = CapabilityContext(memory=mem, mode="chat", user_request="app")
    result = run_capability(
        "cap.dev.light_coding_context@v1",
        ctx,
        {"repo_root": str(tmp_path), "user_input": "app"},
    )
    assert result.ok, result.error_message
    assert result.data.get("context")


def test_capability_batch_skips_executor(tmp_agent_dirs, capability_env, monkeypatch):
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Code.",
        mode="code",
        mode_label="Code",
        plan_dir="Agent-Tasks",
        memory=mem,
    )
    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.sync_project_to_disk",
        lambda: "✅ Synced project to disk",
    )
    batch = engine._execute_capability_batch(
        [{"id": "cap.dev.sync_project@v1", "arguments": {}}],
        task_name="code_cap_parity",
        step_kind="finalize",
        step_index=0,
        source_registry=None,
    )
    assert batch["executed"] >= 1
    engine.executor.execute.assert_not_called()


def test_expand_dynamic_code_plan_attaches_ids(capability_env):
    plan, note = expand_dynamic_code_plan({"steps": []}, "Implement feature X")
    assert "Dynamic code plan" in note
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["capability_id"] == "cap.dev.edit_apply@v1"
    assert plan["steps"][1]["capability_id"] == "cap.dev.sync_project@v1"


def test_code_work_checklist_complete():
    from agent.core.implementation_plan import code_work_checklist_complete
    from agent.core.run_state import ChecklistItemState

    incomplete = [
        ChecklistItemState(id="setup-1", text="setup", status="done"),
        ChecklistItemState(id="tests-1", text="tests", status="pending"),
    ]
    assert code_work_checklist_complete(incomplete) is False
    complete = [
        ChecklistItemState(id="setup-1", text="setup", status="done"),
        ChecklistItemState(id="tests-1", text="tests", status="done"),
        ChecklistItemState(id="impl-1", text="impl", status="done"),
        ChecklistItemState(id="test-1", text="test", status="done"),
        ChecklistItemState(id="docs-1", text="docs", status="pending"),
    ]
    assert code_work_checklist_complete(complete) is True


def test_code_policy_auto_advance_after_passing_tests_on_work():
    policy = CapabilityCodePolicy(mode="code", step_kind="work")
    assert policy.should_auto_advance_after_capability(
        "cap.dev.run_tests@v1",
        True,
        step_kind="work",
        result_summary="3 passed, 0 failed",
    )


def test_code_policy_auto_advance_tdd_red_test_file():
    policy = CapabilityCodePolicy(mode="code", step_kind="tdd_red")
    assert policy.should_auto_advance_after_capability(
        "cap.dev.create_file@v1",
        True,
        step_kind="tdd_red",
        result_data={"file_path": "tests/test_habit.py"},
    )
    assert not policy.should_auto_advance_after_capability(
        "cap.dev.create_file@v1",
        True,
        step_kind="tdd_red",
        result_data={"file_path": "habit.py"},
    )
