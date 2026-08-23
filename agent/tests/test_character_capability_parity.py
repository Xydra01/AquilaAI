"""
Parity tests for capability-only character_build mode.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities.base import CapabilityContext
from agent.capabilities import get_capability, run_capability
from agent.core import LoopEngine
from agent.core.plan_validator import validate_and_tune_plan
from agent.functions.persona import resolve_recipe
from agent.policies import CapabilityPersonaPolicy, get_step_policy
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


def test_persona_capabilities_registered():
    for cap_id in (
        "cap.persona.gather_lore@v1",
        "cap.persona.ingest_sources@v1",
        "cap.persona.write_initialization@v1",
        "cap.persona.finalize@v1",
    ):
        assert get_capability(cap_id) is not None


def test_persona_recipe_and_plan_attach_capability_ids():
    recipe = resolve_recipe(persona_research_lore=False)
    assert recipe.recipe_id == "fn.persona.build"
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "ingest", "status": "pending", "step_kind": "read"},
            {"description": "write", "status": "pending", "step_kind": "synthesize"},
            {"description": "done", "status": "pending", "step_kind": "finalize"},
        ],
    }
    tuned, _notes = validate_and_tune_plan(
        plan, "character_build", "Build a friendly tutor persona"
    )
    assert tuned.get("capability_recipe") == "fn.persona.build"
    for step in tuned["steps"]:
        assert step.get("capability_id"), step


def test_persona_lore_recipe():
    recipe = resolve_recipe(persona_research_lore=True)
    assert recipe.recipe_id == "fn.persona.build_with_lore"
    assert "cap.persona.gather_lore@v1" in recipe.capability_ids


def test_persona_policy_blocks_write_on_read():
    policy = get_step_policy("character_build", "read")
    assert isinstance(policy, CapabilityPersonaPolicy)
    msg = policy.validate_capability_call("cap.persona.write_initialization@v1")
    assert msg and "OS BLOCK" in msg
    assert policy.should_auto_advance_after_capability(
        "cap.persona.ingest_sources@v1", True, step_kind="read"
    )


def test_loop_uses_capabilities_not_tools(tmp_agent_dirs, capability_env, monkeypatch):
    monkeypatch.setattr(
        "agent.core.main.agent_data_path",
        lambda *parts: tmp_agent_dirs.joinpath(*parts),
    )
    task = "persona_cap_parity"
    ledger = tmp_agent_dirs / "Agent-Plans" / f"{task}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{
                "description": "Ingest persona sources",
                "status": "pending",
                "step_kind": "read",
                "capability_id": "cap.persona.ingest_sources@v1",
                "max_iterations": 4,
            }],
        }),
        encoding="utf-8",
    )
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Persona builder.",
        mode="character_build",
        mode_label="Character",
        plan_dir="Agent-Plans",
        memory=mem,
        base_tools={"save_research_note": {"func": MagicMock(), "description": "note"}},
    )
    assert engine._uses_capability_act() is True
    schema = engine._schema_for_capability_step("read", is_final_step=False)
    props = schema.get("properties") or {}
    assert "capabilities" in props
    assert "tools" not in props

    parse_calls: list[dict] = []

    def _track_parse(*_args, **kwargs):
        parse_calls.append(kwargs)
        return {
            "reasoning": "Ingest sources.",
            "capabilities": [{
                "id": "cap.persona.ingest_sources@v1",
                "arguments": {"topic": "Friendly tutor", "content": "Warm, patient teacher."},
            }],
        }

    monkeypatch.setattr("agent.core.loop_engine.parse_agent_response", _track_parse)
    engine.client.chat.return_value = {
        "message": {"content": '{"reasoning":"x","capabilities":[]}'}
    }

    # Drive one act via capability batch helper (full loop needs more wiring).
    ctx_batch = engine._execute_capability_batch(
        [{"id": "cap.persona.ingest_sources@v1", "arguments": {
            "topic": "Friendly tutor",
            "content": "Warm, patient teacher who loves history.",
        }}],
        task_name=task,
        step_kind="read",
        step_index=0,
        source_registry=None,
    )
    assert ctx_batch["executed"] >= 1
    engine.executor.execute.assert_not_called()


def test_ingest_capability_writes_note(tmp_agent_dirs, capability_env, monkeypatch):
    monkeypatch.setattr(
        "agent.core.main.agent_data_path",
        lambda *parts: tmp_agent_dirs.joinpath(*parts),
        raising=False,
    )
    monkeypatch.setattr(
        "agent.tool_library.agent_tools.agent_data_path",
        lambda *parts: tmp_agent_dirs.joinpath(*parts),
        raising=False,
    )
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    ctx = CapabilityContext(
        memory=mem,
        task_id="persona_ingest",
        mode="character_build",
        user_request="Build Alex the explorer",
        attachment_text_chunks=["Alex loves maps and hiking."],
    )
    result = run_capability(
        "cap.persona.ingest_sources@v1",
        ctx,
        {"topic": "Alex the explorer"},
    )
    assert result.ok, result.error_message
