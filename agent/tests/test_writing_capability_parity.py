"""Parity tests for capability-only writing mode."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities.base import CapabilityContext
from agent.capabilities import get_capability, run_capability
from agent.core import LoopEngine
from agent.core.plan_validator import validate_and_tune_plan
from agent.functions.writing import resolve_recipe
from agent.policies import CapabilityWritingPolicy, get_step_policy
from agent.storage import DualMemorySystem


@pytest.fixture
def capability_env(monkeypatch):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "0")
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    monkeypatch.setenv("AQUILA_AUTO_ADVANCE_MILESTONES", "1")
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "0")
    monkeypatch.setattr(
        "agent.storage.preferences.apply_preferences_to_environ",
        lambda *args, **kwargs: None,
    )


def test_writing_capabilities_registered():
    for cap_id in (
        "cap.writing.init_document@v1",
        "cap.writing.draft_sections@v1",
        "cap.writing.read_outline@v1",
        "cap.writing.compile_document@v1",
        "cap.writing.finalize_deliverable@v1",
        "cap.plan.generate_writing@v1",
    ):
        assert get_capability(cap_id) is not None


def test_writing_recipe_and_plan_attach(capability_env):
    recipe = resolve_recipe(dynamic_loop=True)
    assert recipe.recipe_id == "fn.writing.dynamic_work"
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "draft", "status": "pending", "step_kind": "write"},
            {"description": "done", "status": "pending", "step_kind": "finalize"},
        ],
    }
    tuned, _ = validate_and_tune_plan(plan, "writing", "Essay on generation lock")
    assert tuned.get("capability_recipe") == "fn.writing.dynamic_work"
    for step in tuned["steps"]:
        assert step.get("capability_id"), step


def test_writing_policy_blocks_finalize_on_write():
    policy = get_step_policy("writing", "write")
    assert isinstance(policy, CapabilityWritingPolicy)
    msg = policy.validate_capability_call("cap.writing.finalize_deliverable@v1")
    assert msg and "OS BLOCK" in msg


def test_writing_policy_blocks_draft_on_finalize():
    policy = get_step_policy("writing", "finalize")
    msg = policy.validate_capability_call("cap.writing.draft_sections@v1")
    assert msg and "OS BLOCK" in msg


def test_loop_uses_capabilities_not_tools(tmp_agent_dirs, capability_env):
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Writing mode.",
        mode="writing",
        mode_label="Writing",
        plan_dir="Agent-Tasks",
        memory=mem,
        base_tools={"write_section": {"func": MagicMock(), "description": "legacy"}},
    )
    assert engine._uses_capability_act() is True
    schema = engine._schema_for_capability_step("write", is_final_step=False)
    props = schema.get("properties") or {}
    assert "capabilities" in props
    assert "tools" not in props


def test_draft_sections_capability(tmp_agent_dirs, capability_env, monkeypatch):
    draft_dir = tmp_agent_dirs / "Agent-Drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    active = draft_dir / "active_draft_state.json"
    monkeypatch.setattr(
        "agent.tool_library.writing_tools.DRAFT_DIR",
        draft_dir,
    )
    monkeypatch.setattr(
        "agent.tool_library.writing_tools.ACTIVE_DRAFT_FILE",
        active,
    )
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    ctx = CapabilityContext(
        memory=mem,
        task_id="writing_draft",
        mode="writing",
        user_request="Aquila Generation Lock",
    )
    result = run_capability(
        "cap.writing.draft_sections@v1",
        ctx,
        {
            "section_header": "Introduction",
            "content": "Generation lock ensures one run at a time.",
        },
    )
    assert result.ok, result.error_message
    assert active.is_file()


def test_finalize_deliverable_compiles(tmp_agent_dirs, capability_env, monkeypatch):
    draft_dir = tmp_agent_dirs / "Agent-Drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    active = draft_dir / "active_draft_state.json"
    active.write_text(
        json.dumps({
            "title": "Test Doc",
            "synopsis": "",
            "sections": [{"header": "Intro", "content": "Body text here."}],
            "word_count": 3,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("agent.tool_library.writing_tools.DRAFT_DIR", draft_dir)
    monkeypatch.setattr("agent.tool_library.writing_tools.ACTIVE_DRAFT_FILE", active)
    monkeypatch.setattr("agent.capabilities.writing.finalize_deliverable.DRAFT_DIR", draft_dir)
    monkeypatch.setattr("agent.capabilities.writing.finalize_deliverable.ACTIVE_DRAFT_FILE", active)
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    ctx = CapabilityContext(
        memory=mem,
        task_id="writing_finalize",
        mode="writing",
        user_request="Test Doc",
    )
    result = run_capability(
        "cap.writing.finalize_deliverable@v1",
        ctx,
        {"file_name": "test-doc"},
    )
    assert result.ok, result.error_message
    assert (draft_dir / "test-doc.md").is_file()
    assert not active.exists()


def test_capability_batch_skips_executor(tmp_agent_dirs, capability_env, monkeypatch):
    draft_dir = tmp_agent_dirs / "Agent-Drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("agent.tool_library.writing_tools.DRAFT_DIR", draft_dir)
    monkeypatch.setattr(
        "agent.tool_library.writing_tools.ACTIVE_DRAFT_FILE",
        draft_dir / "active_draft_state.json",
    )
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Writing.",
        mode="writing",
        mode_label="Writing",
        plan_dir="Agent-Tasks",
        memory=mem,
    )
    batch = engine._execute_capability_batch(
        [{
            "id": "cap.writing.draft_sections@v1",
            "arguments": {
                "section_header": "Chapter 1",
                "content": "Draft paragraph.",
                "title": "Parity Essay",
            },
        }],
        task_name="writing_cap_parity",
        step_kind="write",
        step_index=0,
        source_registry=None,
    )
    assert batch["executed"] >= 1
    engine.executor.execute.assert_not_called()
