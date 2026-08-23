"""
Parity tests for capability-only learn_syllabus_build mode.
"""
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
from agent.functions.learn import resolve_recipe
from agent.policies import CapabilityLearnPolicy, get_step_policy
from agent.storage import DualMemorySystem
from agent.tool_library import learn_tools


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


MIN_SYLLABUS = json.dumps({
    "version": 1,
    "status": "building",
    "nodes": [
        {
            "id": "n1",
            "title": "Intro",
            "description": "Basics",
            "prerequisites": [],
            "mastery_tiers": [
                {"tier": 1, "label": "Recall", "criteria": "Remember terms"},
                {"tier": 2, "label": "Apply", "criteria": "Use concepts"},
            ],
        },
        {
            "id": "n2",
            "title": "Core",
            "description": "Core ideas",
            "prerequisites": ["n1"],
            "mastery_tiers": [
                {"tier": 1, "label": "Recall", "criteria": "List ideas"},
                {"tier": 2, "label": "Apply", "criteria": "Solve problems"},
            ],
        },
        {
            "id": "n3",
            "title": "Advanced",
            "description": "Deeper work",
            "prerequisites": ["n2"],
            "mastery_tiers": [
                {"tier": 1, "label": "Recall", "criteria": "Explain"},
                {"tier": 2, "label": "Apply", "criteria": "Create"},
            ],
        },
    ],
})


def test_learn_capabilities_registered():
    for cap_id in (
        "cap.learn.gather_topic_sources@v1",
        "cap.learn.ingest_course_materials@v1",
        "cap.learn.write_syllabus@v1",
        "cap.learn.generate_assessments@v1",
        "cap.learn.finalize_course@v1",
    ):
        assert get_capability(cap_id) is not None


def test_learn_recipe_and_plan_attach():
    recipe = resolve_recipe(learn_syllabus_web=False)
    assert recipe.recipe_id == "fn.learn.syllabus"
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "ingest", "status": "pending", "step_kind": "read"},
            {"description": "write", "status": "pending", "step_kind": "synthesize"},
            {"description": "done", "status": "pending", "step_kind": "finalize"},
        ],
    }
    tuned, _ = validate_and_tune_plan(plan, "learn_syllabus_build", "Intro to Python")
    assert tuned.get("capability_recipe") == "fn.learn.syllabus"
    for step in tuned["steps"]:
        assert step.get("capability_id"), step


def test_learn_web_recipe():
    recipe = resolve_recipe(learn_syllabus_web=True)
    assert recipe.recipe_id == "fn.learn.syllabus_web"
    assert "cap.learn.gather_topic_sources@v1" in recipe.capability_ids


def test_learn_policy_blocks_write_on_search():
    policy = get_step_policy("learn_syllabus_build", "search", learn_syllabus_web=True)
    assert isinstance(policy, CapabilityLearnPolicy)
    msg = policy.validate_capability_call("cap.learn.write_syllabus@v1")
    assert msg and "OS BLOCK" in msg


def test_loop_schema_capability_action(tmp_agent_dirs, capability_env):
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Learn builder.",
        mode="learn_syllabus_build",
        mode_label="Learn",
        plan_dir="Agent-Plans",
        memory=mem,
        base_tools={},
        learn_syllabus_web=True,
    )
    assert engine._uses_capability_act() is True
    schema = engine._schema_for_capability_step("search", is_final_step=False)
    assert "capabilities" in (schema.get("properties") or {})
    assert "tools" not in (schema.get("properties") or {})


def test_write_syllabus_capability(tmp_agent_dirs, capability_env, monkeypatch):
    monkeypatch.setattr(
        "agent.storage.learn_registry.agent_data_path",
        lambda *parts: tmp_agent_dirs.joinpath(*parts),
        raising=False,
    )
    monkeypatch.setattr(
        "agent.storage.workspace_paths.agent_data_path",
        lambda *parts: tmp_agent_dirs.joinpath(*parts),
        raising=False,
    )
    from agent.storage import create_course, save_course

    # Use learn_tools active session
    iid, cid = "default", "course_parity"
    learn_tools.set_active_syllabus_build(iid, cid)
    try:
        # Ensure course record exists if API requires it
        try:
            from agent.storage.learn_registry import Course, save_course as _save

            course = Course(id=cid, title="Parity Course", build_complete=False)
            _save(iid, course)
        except Exception:
            pass

        mem = DualMemorySystem(
            storage_dir=str(tmp_agent_dirs / "mem"), instance_id=iid
        )
        ctx = CapabilityContext(
            memory=mem,
            task_id="learn_write",
            mode="learn_syllabus_build",
            user_request="Intro to Python",
            instance_id=iid,
        )
        with patch(
            "agent.tool_library.learn_tools.save_syllabus",
            return_value=None,
        ), patch(
            "agent.tool_library.learn_tools.validate_syllabus_structure",
            return_value=(True, ""),
        ), patch(
            "agent.tool_library.learn_tools.syllabus_ready",
            return_value=False,
        ), patch(
            "agent.tool_library.learn_tools.get_active_syllabus_build",
            return_value={"instance_id": iid, "course_id": cid, "syllabus_written": False},
        ):
            # Bypass complex storage: call handler validation path with mocked write
            with patch(
                "agent.capabilities.learn.write_syllabus.write_syllabus_file",
                return_value="✅ Wrote syllabus with 3 node(s).",
            ):
                result = run_capability(
                    "cap.learn.write_syllabus@v1",
                    ctx,
                    {"content": MIN_SYLLABUS},
                )
        assert result.ok, result.error_message
    finally:
        learn_tools.clear_active_syllabus_build()


def test_ingest_course_materials(tmp_agent_dirs, capability_env, monkeypatch):
    monkeypatch.setattr(
        "agent.tool_library.agent_tools.agent_data_path",
        lambda *parts: tmp_agent_dirs.joinpath(*parts),
        raising=False,
    )
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    ctx = CapabilityContext(
        memory=mem,
        task_id="learn_ingest",
        mode="learn_syllabus_build",
        user_request="Intro to Python",
        attachment_text_chunks=["Variables, loops, and functions."],
    )
    result = run_capability(
        "cap.learn.ingest_course_materials@v1",
        ctx,
        {"topic": "Intro to Python"},
    )
    assert result.ok, result.error_message
