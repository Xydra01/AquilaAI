"""Living implementation plan (design plane) tests."""
from __future__ import annotations

from agent.capabilities.adapters import allowed_capabilities_for_step
from agent.core.implementation_plan import (
    ensure_implementation_block,
    format_implementation_for_act,
    render_implementation_plan_markdown,
    scaffold_implementation,
    should_write_living_plan,
    update_checklist_items,
)
from agent.core.plan_validator import (
    build_fallback_code_plan,
    build_fallback_research_plan,
    build_fallback_writing_plan,
)
from agent.core.task_artifacts import (
    implementation_plan_md_path,
    write_plan_artifact,
)


def test_scaffold_code_has_checklist():
    impl = scaffold_implementation(mode="code", user_request="Build a counter")
    assert impl["checklist"]
    assert impl["acceptance"]


def test_ensure_merges_llm_checklist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan = {
        "user_goal": "Build habit tracker",
        "approach_summary": "TDD then sync",
        "steps": [{"step_kind": "work", "description": "work", "status": "pending"}],
        "implementation": {
            "summary": "Custom summary",
            "checklist": [{"id": "a", "text": "Add habit.py", "status": "pending"}],
            "files_create": ["habit.py"],
        },
    }
    ensure_implementation_block(plan, "code", user_request="Build habit tracker")
    assert plan["implementation"]["summary"] == "Custom summary"
    assert plan["implementation"]["files_create"] == ["habit.py"]
    assert plan["implementation"]["checklist"][0]["id"] == "a"


def test_micro_plan_skips_living():
    assert not should_write_living_plan({"micro_plan": True}, "code")
    assert should_write_living_plan({"micro_plan": False}, "writing")


def test_write_plan_artifact_creates_implementation_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan = {
        "user_goal": "Write a short essay",
        "approach_summary": "Draft then finalize",
        "steps": [
            {"step_kind": "write", "description": "Draft", "status": "pending"},
            {"step_kind": "finalize", "description": "Finalize", "status": "pending"},
        ],
        "micro_plan": False,
    }
    write_plan_artifact("essay_task", "writing", plan, user_request="Write a short essay")
    impl_path = implementation_plan_md_path("essay_task", "writing")
    assert impl_path.exists()
    text = impl_path.read_text(encoding="utf-8")
    assert "Implementation Plan" in text
    assert "Checklist" in text
    from agent.core.task_artifacts import read_plan_dict

    loaded = read_plan_dict("essay_task", "writing")
    assert loaded.get("implementation", {}).get("checklist")


def test_render_and_act_format():
    plan = {
        "user_goal": "Research topic X",
        "implementation": scaffold_implementation(
            mode="research", user_request="Research topic X"
        ),
    }
    md = render_implementation_plan_markdown(plan, mode="research")
    assert "Research questions" in md or "Checklist" in md
    act = format_implementation_for_act(plan)
    assert "checklist" in act.lower() or "Checklist" in act or "Next checklist" in act


def test_update_checklist_items():
    plan = {
        "user_goal": "g",
        "implementation": scaffold_implementation(mode="code", user_request="g"),
    }
    first_id = plan["implementation"]["checklist"][0]["id"]
    plan, n = update_checklist_items(plan, mode="code", item_ids=[first_id], status="done")
    assert n == 1
    assert plan["implementation"]["checklist"][0]["status"] == "done"


def test_fallbacks_include_implementation():
    code, _ = build_fallback_code_plan("Implement feature X", dynamic_loop=True)
    assert code.get("implementation", {}).get("checklist")
    writing, _ = build_fallback_writing_plan("Write a memo", dynamic_loop=True)
    assert writing.get("implementation", {}).get("checklist")
    research, _ = build_fallback_research_plan("Explain gravity")
    assert research.get("implementation", {}).get("checklist")


def test_plan_caps_on_work_allowlists():
    for mode, kind in (
        ("code", "work"),
        ("writing", "write"),
        ("research", "work"),
        ("learn_syllabus_build", "synthesize"),
        ("character_build", "synthesize"),
    ):
        allowed = allowed_capabilities_for_step(kind, mode=mode)
        assert "cap.plan.update_checklist@v1" in allowed
        assert "cap.plan.read_implementation@v1" in allowed


def test_update_checklist_capability(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from agent.capabilities import run_capability
    from agent.capabilities.base import CapabilityContext
    from agent.core.task_artifacts import read_plan_dict

    plan = {
        "user_goal": "Build thing",
        "steps": [{"step_kind": "work", "description": "w", "status": "pending"}],
    }
    write_plan_artifact("cap_task", "code", plan, user_request="Build thing")
    plan = read_plan_dict("cap_task", "code")
    first = plan["implementation"]["checklist"][0]["id"]
    ctx = CapabilityContext(task_id="cap_task", mode="code", user_request="Build thing")
    result = run_capability(
        "cap.plan.update_checklist@v1",
        ctx,
        {"item_ids": [first], "status": "done"},
    )
    assert result.ok
    assert result.data.get("updated", 0) >= 1
    reloaded = read_plan_dict("cap_task", "code")
    assert reloaded["implementation"]["checklist"][0]["status"] == "done"
