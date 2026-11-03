"""Tests for unified TaskRunContext / RunState."""
from __future__ import annotations

import json
import os

import pytest

from agent.capabilities.base import CapabilityResult
from agent.core.run_state import TaskRunContext
from agent.core.task_artifacts import run_state_path, write_plan_artifact
from agent.policies.context_budget import resolve_context_profile


@pytest.fixture
def code_plan(tmp_agent_dirs):
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "user_goal": "Build a habit tracker CLI",
        "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        "implementation": {
            "summary": "TDD habit tracker",
            "checklist": [
                {"id": "setup-1", "text": "Init project", "status": "pending"},
                {"id": "tests-1", "text": "Write tests", "status": "pending"},
                {"id": "impl-1", "text": "Implement", "status": "pending"},
            ],
        },
    }
    write_plan_artifact("habit-task", "code", plan)
    return plan


def test_run_state_persist_and_load(tmp_agent_dirs, code_plan):
    ctx = TaskRunContext.bootstrap(
        task_id="habit-task",
        mode="code",
        goal="Build a habit tracker CLI",
    )
    ctx.persist()
    path = run_state_path("habit-task", "code")
    assert path.is_file()
    loaded = TaskRunContext.load(
        "habit-task",
        "code",
        goal="Build a habit tracker CLI",
    )
    assert loaded.task_id == "habit-task"
    assert loaded.goal == "Build a habit tracker CLI"
    assert len(loaded.checklist) == 3


def test_checkpoint_updates_digest_and_persists(tmp_agent_dirs, code_plan, monkeypatch):
    monkeypatch.setenv("AQUILA_RUN_DIGEST_COMPRESS", "0")
    ctx = TaskRunContext.bootstrap(
        task_id="habit-task",
        mode="code",
        goal="Build a habit tracker CLI",
    )
    result = CapabilityResult.success(
        summary="Created tests/test_habit.py",
        file_path="tests/test_habit.py",
    )
    meta = ctx.checkpoint_capability(
        cap_id="cap.dev.create_file@v1",
        result=result,
        summary_text="Created tests/test_habit.py",
        client=None,
        profile=resolve_context_profile(num_ctx_override=32768),
    )
    assert meta["digest_len"] > 0
    assert ctx.last_capability is not None
    assert ctx.last_capability.ok
    assert "cap.dev.create_file@v1" in ctx.run_digest

    raw = json.loads(run_state_path("habit-task", "code").read_text(encoding="utf-8"))
    assert raw["last_capability"]["cap_id"] == "cap.dev.create_file@v1"


def test_checkpoint_auto_ticks_test_checklist(tmp_agent_dirs, code_plan):
    ctx = TaskRunContext.bootstrap(
        task_id="habit-task",
        mode="code",
        goal="Build a habit tracker CLI",
    )
    result = CapabilityResult.success(
        summary="ok",
        file_path="tests/test_habit.py",
    )
    ctx.checkpoint_capability(
        cap_id="cap.dev.create_file@v1",
        result=result,
        summary_text="Created test file",
        client=None,
        profile=resolve_context_profile(num_ctx_override=32768),
    )
    done_ids = {c.id for c in ctx.checklist if c.status == "done"}
    assert "tests-1" in done_ids


def test_render_for_prompt_goal_once(tmp_agent_dirs, code_plan):
    ctx = TaskRunContext.bootstrap(
        task_id="habit-task",
        mode="code",
        goal="Build a habit tracker CLI with JSON persistence",
    )
    ctx.episode = 0
    full = ctx.render_for_prompt(include_full_goal=True)
    assert "habit tracker" in full.lower()
    assert "RUN STATE" in full

    ctx.episode = 2
    ctx.run_digest = "- [cap.dev.project_setup@v1] OK: setup done"
    summary_only = ctx.render_for_prompt(include_full_goal=False)
    assert "Goal (summary)" in summary_only
    assert "JSON persistence" not in summary_only or "summary" in summary_only.lower()


def test_build_turn_messages_injects_run_state(tmp_agent_dirs, code_plan, monkeypatch):
    monkeypatch.setenv("AQUILA_RUN_STATE_ENABLED", "1")
    ctx = TaskRunContext.bootstrap(
        task_id="habit-task",
        mode="code",
        goal="Build habit tracker",
    )
    ctx.run_digest = "- setup complete"
    msgs = ctx.build_turn_messages(
        system_prompt="You are Aquila.",
        step_entry=[],
        conversation_history=[],
        user_message={"role": "user", "content": "act"},
        profile=resolve_context_profile(num_ctx_override=32768),
    )
    joined = "\n".join(
        m.get("content", "") if isinstance(m.get("content"), str) else ""
        for m in msgs
    )
    assert "RUN STATE" in joined
    assert "WORKSPACE SUMMARY" not in joined
