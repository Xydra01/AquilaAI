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


def test_run_unified_task_pauses_for_plan_review(agent_env, monkeypatch):
    from agent.core.main import Agent

    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_PLAN_AUTO_APPROVE_MICRO", "0")
    monkeypatch.setenv("AQUILA_FAST_PATH", "0")

    agent = Agent.__new__(Agent)
    agent.instance_id = "default"
    agent.client = MagicMock()
    agent.client.warmup.return_value = (True, "ok")
    agent.executor = MagicMock()
    agent.memory = MagicMock()
    agent.memory.route_tools = MagicMock(return_value=[])
    agent.base_tools = {"web_search": {"func": lambda: None, "description": "s"}}
    agent.action_schema = {}
    agent.mcp_bridge = None

    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "approval_status": "draft",
        "steps": [{"description": "x", "step_kind": "work", "max_iterations": 4}],
    }
    plan_json = json.dumps(plan)

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
