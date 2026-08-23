"""Plan review gate tests."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.task_artifacts import PLAN_REVIEW_SENTINEL, extract_plan_review_result


def test_extract_plan_review_result_from_wrapped_worker_text():
    raw = f"{PLAN_REVIEW_SENTINEL}|iwantyou_1783631812|research"
    wrapped = f"✅ Task Completed:\n{raw}"
    assert extract_plan_review_result(wrapped) == raw
    assert extract_plan_review_result(raw) == raw
    assert extract_plan_review_result("✅ Task Completed:\nnothing here") is None


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_SKIP_WARMUP", "1")
    (tmp_path / "Agent-Tasks").mkdir(parents=True)
    return tmp_path


def _stub_agent(*, with_web: bool = False):
    from agent.core.main import Agent

    agent = Agent.__new__(Agent)
    agent.instance_id = "default"
    agent.client = MagicMock()
    agent.client.warmup.return_value = (True, "ok")
    agent.executor = MagicMock()
    agent.memory = MagicMock()
    agent.memory.route_tools = MagicMock(return_value=[])
    agent._tools_ready = True
    agent._base_tools = (
        {"web_search": {"func": lambda: None, "description": "s"}} if with_web else {}
    )
    agent.action_schema = {}
    agent.mcp_bridge = None
    agent.instance_profile = {}
    return agent


def test_run_unified_task_pauses_for_plan_review(agent_env, monkeypatch):
    from agent.core.main import Agent

    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_PLAN_AUTO_APPROVE_MICRO", "0")
    monkeypatch.setenv("AQUILA_FAST_PATH", "0")

    agent = _stub_agent(with_web=True)
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "approval_status": "draft",
        "steps": [{"description": "x", "step_kind": "work", "max_iterations": 4}],
    }
    plan_json = json.dumps(plan)

    with patch.object(Agent, "ensure_tools_ready", return_value=None):
        with patch.object(Agent, "generate_plan", return_value=plan_json):
            with patch.object(Agent, "_system_prompt_for_mode", return_value="sys"):
                with patch("agent.core.main.console"):
                    result = Agent._run_unified_task_impl(
                        agent,
                        "review_task",
                        "do something that requires a full multi-step plan with delegation",
                        "task",
                    )

    assert result.startswith(PLAN_REVIEW_SENTINEL)


def test_auto_approve_when_review_disabled(agent_env, monkeypatch):
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "0")
    from agent.core.task_artifacts import plan_needs_review

    assert plan_needs_review({"approval_status": "draft"}) is False


def test_character_build_approve_does_not_regenerate_plan(agent_env, monkeypatch):
    """Approve must run the existing plan — not wipe and re-plan (review loop bug)."""
    from agent.core.main import Agent
    from agent.core.task_artifacts import approve_plan, write_plan_artifact

    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_FAST_PATH", "0")
    monkeypatch.setattr(
        "agent.storage.preferences.apply_preferences_to_environ",
        lambda *a, **k: None,
    )

    task = "persona_build_loopfix"
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "approval_status": "draft",
        "steps": [
            {
                "description": "ingest",
                "status": "pending",
                "step_kind": "read",
                "capability_id": "cap.persona.ingest_sources@v1",
                "max_iterations": 4,
            },
            {
                "description": "write",
                "status": "pending",
                "step_kind": "synthesize",
                "capability_id": "cap.persona.write_initialization@v1",
                "max_iterations": 4,
            },
            {
                "description": "finalize",
                "status": "pending",
                "step_kind": "finalize",
                "capability_id": "cap.persona.finalize@v1",
                "max_iterations": 4,
            },
        ],
    }
    write_plan_artifact(task, "character_build", plan, user_request="Build Alex")
    approve_plan(task, "character_build")

    agent = _stub_agent()
    gen = MagicMock(side_effect=AssertionError("generate_plan must not run after approve"))
    loop_result = "✅ Persona build complete"

    class _FakeEngine:
        def __init__(self, *a, **k):
            pass

        def run(self, **kwargs):
            return loop_result

    with patch.object(Agent, "ensure_tools_ready", return_value=None):
        with patch.object(Agent, "generate_plan", gen):
            with patch.object(Agent, "_system_prompt_for_mode", return_value="sys"):
                with patch("agent.core.main.console"):
                    with patch("agent.core.loop_engine.LoopEngine", _FakeEngine):
                        with patch("tool_library.persona_tools.set_active_persona_build"):
                            with patch(
                                "tool_library.persona_tools.clear_active_persona_build"
                            ):
                                with patch(
                                    "agent.storage.persona_dir",
                                    return_value=agent_env / "persona",
                                ):
                                    (agent_env / "persona").mkdir(
                                        parents=True, exist_ok=True
                                    )
                                    result = Agent._run_unified_task_impl(
                                        agent,
                                        task,
                                        "Build Alex",
                                        "character_build",
                                        execute_approved=True,
                                    )

    assert result == loop_result
    assert not gen.called
    assert PLAN_REVIEW_SENTINEL not in result


def test_learn_syllabus_approve_does_not_regenerate_plan(agent_env, monkeypatch):
    from agent.core.main import Agent
    from agent.core.task_artifacts import approve_plan, write_plan_artifact

    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    task = "syllabus_build_loopfix"
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "approval_status": "draft",
        "steps": [
            {
                "description": "ingest",
                "status": "pending",
                "step_kind": "read",
                "capability_id": "cap.learn.ingest_course_materials@v1",
                "max_iterations": 4,
            },
            {
                "description": "write",
                "status": "pending",
                "step_kind": "synthesize",
                "capability_id": "cap.learn.write_syllabus@v1",
                "max_iterations": 4,
            },
            {
                "description": "finalize",
                "status": "pending",
                "step_kind": "finalize",
                "capability_id": "cap.learn.finalize_course@v1",
                "max_iterations": 4,
            },
        ],
    }
    write_plan_artifact(task, "learn_syllabus_build", plan, user_request="Python 101")
    approve_plan(task, "learn_syllabus_build")

    agent = _stub_agent()
    gen = MagicMock(side_effect=AssertionError("generate_plan must not run after approve"))

    class _FakeEngine:
        def __init__(self, *a, **k):
            pass

        def run(self, **kwargs):
            return "✅ Course finalized"

    with patch.object(Agent, "ensure_tools_ready", return_value=None):
        with patch.object(Agent, "generate_plan", gen):
            with patch.object(Agent, "_system_prompt_for_mode", return_value="sys"):
                with patch("agent.core.main.console"):
                    with patch("agent.core.loop_engine.LoopEngine", _FakeEngine):
                        with patch("tool_library.learn_tools.set_active_syllabus_build"):
                            with patch(
                                "tool_library.learn_tools.clear_active_syllabus_build"
                            ):
                                with patch(
                                    "agent.storage.course_dir",
                                    return_value=agent_env / "course",
                                ):
                                    (agent_env / "course").mkdir(
                                        parents=True, exist_ok=True
                                    )
                                    result = Agent._run_unified_task_impl(
                                        agent,
                                        task,
                                        "Python 101",
                                        "learn_syllabus_build",
                                        execute_approved=True,
                                    )

    assert "✅" in result
    assert not gen.called
    assert PLAN_REVIEW_SENTINEL not in result
