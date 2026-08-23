import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    harness_force_micro_plan,
    build_micro_plan,
    explore_brief_enabled,
    should_micro_plan,
)


def test_should_micro_plan_simple_code():
    assert should_micro_plan("code", "Create hello_aquila.py that prints hello")


def test_should_micro_plan_rejects_complex():
    assert not should_micro_plan(
        "code",
        "Refactor the entire multi-file architecture for autonomous task orchestration",
    )


def test_should_micro_plan_rejects_attachments():
    assert not should_micro_plan("code", "fix bug", text_chunks=["file content"])


def test_harness_force_micro_plan_env(monkeypatch):
    monkeypatch.setenv("AQUILA_HARNESS_FORCE_MICRO_PLAN", "1")
    assert harness_force_micro_plan()
    assert should_micro_plan(
        "code",
        "Refactor the entire multi-file architecture for autonomous task orchestration",
    )


def test_build_micro_plan_code_has_two_steps():
    raw = build_micro_plan("code", "add function add(a,b)", "task1")
    plan = json.loads(raw)
    assert plan.get("micro_plan") is True
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["step_kind"] == "code"


def test_explore_brief_disabled_for_micro_plan():
    os.environ["AQUILA_EXPLORE_BRIEF"] = "1"
    assert not explore_brief_enabled("code", "simple task", micro_plan=True)


def test_research_micro_plan_steps():
    raw = build_micro_plan("research", "Summarize local LLM costs", "r1")
    plan = json.loads(raw)
    kinds = [s["step_kind"] for s in plan["steps"]]
    assert kinds == ["search", "synthesize"]


def test_should_micro_plan_rejects_managers():
    assert not should_micro_plan("task", "Simple check files task")
    assert not should_micro_plan("autonomous", "Simple auto task")


def test_should_micro_plan_disabled_when_dynamic_loop(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    assert not should_micro_plan("research", "Summarize local LLM costs")


def test_should_micro_plan_disabled_when_plan_review_without_auto_approve(monkeypatch):
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_PLAN_AUTO_APPROVE_MICRO", "0")
    assert not should_micro_plan("code", "Create hello_aquila.py that prints hello")
