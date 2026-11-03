import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    harness_force_micro_plan,
    build_micro_plan,
    explore_brief_enabled,
    should_micro_plan,
    always_full_plan_enabled,
)


def test_should_micro_plan_code_always_false():
    """Phase 3: code mode never uses micro-plan / slot-fill."""
    assert not should_micro_plan("code", "Create hello_aquila.py that prints hello")
    assert not should_micro_plan(
        "code",
        "Refactor the entire multi-file architecture for autonomous task orchestration",
    )


def test_should_micro_plan_rejects_attachments_research():
    assert not should_micro_plan(
        "research", "Summarize topic", text_chunks=["file content"]
    )


def test_always_full_plan_blocks_micro(monkeypatch):
    monkeypatch.setenv("AQUILA_ALWAYS_FULL_PLAN", "1")
    monkeypatch.setenv("AQUILA_FAST_PATH", "1")
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "0")
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "0")
    assert always_full_plan_enabled()
    assert not should_micro_plan("research", "Summarize local LLM costs")


def test_harness_force_micro_plan_env(monkeypatch):
    monkeypatch.setenv("AQUILA_HARNESS_FORCE_MICRO_PLAN", "1")
    assert harness_force_micro_plan()
    # Code still blocked even when harness forces micro for other modes.
    assert not should_micro_plan("code", "Create hello.py")
    assert should_micro_plan("research", "Summarize local LLM costs briefly")


def test_build_micro_plan_code_empty_steps():
    raw = build_micro_plan("code", "add function add(a,b)", "task1")
    plan = json.loads(raw)
    assert plan.get("micro_plan") is True
    assert plan["steps"] == []


def test_explore_brief_disabled_for_code():
    os.environ["AQUILA_EXPLORE_BRIEF"] = "1"
    assert not explore_brief_enabled("code", "simple task", micro_plan=False)
    assert not explore_brief_enabled("code", "simple task", micro_plan=True)


def test_research_micro_plan_steps(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "0")
    raw = build_micro_plan("research", "Summarize local LLM costs", "r1")
    plan = json.loads(raw)
    kinds = [s["step_kind"] for s in plan["steps"]]
    assert kinds == ["search", "synthesize"]
    assert plan["steps"][0].get("capability_id") == "cap.research.gather_web_sources@v1"
    assert plan["steps"][1].get("capability_id") == "cap.research.synthesize_notes@v1"


def test_writing_dynamic_micro_finalize_no_finish_task(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    raw = build_micro_plan("writing", "Draft a short essay on generation lock", "w_dyn")
    plan = json.loads(raw)
    finalize = plan["steps"][-1]
    assert finalize["step_kind"] == "finalize"
    assert "finish_task" not in finalize["description"].lower()
    assert finalize.get("capability_id") == "cap.writing.finalize_deliverable@v1"
    assert plan["steps"][0].get("capability_id") == "cap.writing.draft_sections@v1"


def test_research_dynamic_micro_finalize_no_finish_task(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    raw = build_micro_plan("research", "Summarize local LLM costs", "r_dyn")
    plan = json.loads(raw)
    finalize = plan["steps"][-1]
    assert finalize["step_kind"] == "finalize"
    assert "finish_task" not in finalize["description"].lower()
    assert finalize.get("capability_id") == "cap.research.finalize_deliverable@v1"


def test_should_micro_plan_rejects_managers():
    assert not should_micro_plan("task", "Simple check files task")
    assert not should_micro_plan("autonomous", "Simple auto task")


def test_should_micro_plan_disabled_when_dynamic_loop(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    assert not should_micro_plan("research", "Summarize local LLM costs")


def test_should_micro_plan_disabled_when_plan_review_without_auto_approve(monkeypatch):
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_PLAN_AUTO_APPROVE_MICRO", "0")
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "0")
    assert not should_micro_plan("research", "Summarize local LLM costs")
