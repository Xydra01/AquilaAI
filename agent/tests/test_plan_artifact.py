"""Plan artifact read/write tests."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.task_artifacts import (
    enrich_plan_from_ledger,
    plan_needs_review,
    render_plan_markdown,
    write_plan_artifact,
)


def test_enrich_plan_adds_approach_and_milestones(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raw = json.dumps(
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        }
    )
    plan = enrich_plan_from_ledger(raw, user_request="Build a widget", mode="code")
    assert plan.get("user_goal")
    assert plan.get("approach_summary")
    assert plan.get("milestones")


def test_enrich_offline_research_milestones_use_offline_hints():
    raw = json.dumps(
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        }
    )
    plan = enrich_plan_from_ledger(
        raw,
        user_request="Summarize PDF",
        mode="research",
        offline_research=True,
        capability_research=True,
    )
    criteria = " ".join(m.get("success_criteria", "") for m in plan["milestones"])
    assert "Capabilities used:" in criteria
    assert "web_search" not in criteria
    assert "ingest_offline" in criteria or "cap.research" in criteria


def test_enrich_capability_research_milestones_deferred_for_character():
    """Learn/character milestones are built after attach in main, not static enrich."""
    raw = json.dumps(
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{"description": "work", "step_kind": "work", "max_iterations": 8}],
        }
    )
    plan = enrich_plan_from_ledger(
        raw,
        user_request="Build persona",
        mode="character_build",
        capability_research=True,
    )
    assert not plan.get("milestones")


def test_build_milestones_from_learn_file_only_steps():
    from agent.core.loop_objectives import build_milestones_from_plan_steps

    steps = [
        {
            "step_kind": "read",
            "capability_id": "cap.learn.ingest_course_materials@v1",
        },
        {
            "step_kind": "synthesize",
            "capability_id": "cap.learn.write_syllabus@v1",
        },
        {
            "step_kind": "finalize",
            "capability_id": "cap.learn.finalize_course@v1",
        },
    ]
    milestones = build_milestones_from_plan_steps(steps, "learn_syllabus_build")
    criteria = " ".join(m["success_criteria"] for m in milestones)
    assert "cap.learn.ingest_course_materials@v1" in criteria
    assert "cap.learn.write_syllabus@v1" in criteria
    assert "cap.learn.finalize_course@v1" in criteria
    assert "gather_topic_sources" not in criteria
    assert "generate_assessments" not in criteria


def test_build_milestones_from_learn_web_steps():
    from agent.core.loop_objectives import build_milestones_from_plan_steps

    steps = [
        {"step_kind": "search", "capability_id": "cap.learn.gather_topic_sources@v1"},
        {"step_kind": "read", "capability_id": "cap.learn.ingest_course_materials@v1"},
        {"step_kind": "synthesize", "capability_id": "cap.learn.write_syllabus@v1"},
        {"step_kind": "finalize", "capability_id": "cap.learn.finalize_course@v1"},
    ]
    milestones = build_milestones_from_plan_steps(steps, "learn_syllabus_build")
    ingest = next(m for m in milestones if m["id"] == "ingest")
    assert "gather_topic_sources" in ingest["success_criteria"]
    assert "ingest_course_materials" in ingest["success_criteria"]


def test_write_plan_artifact_creates_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "user_goal": "Test",
        "approach_summary": "Do the thing.",
        "steps": [],
        "approval_status": "draft",
    }
    json_path, md_path = write_plan_artifact("t1", "task", plan)
    assert os.path.isfile(json_path)
    assert os.path.isfile(md_path)
    md = open(md_path, encoding="utf-8").read()
    assert "Do the thing" in md


def test_plan_needs_review_respects_micro_auto(monkeypatch):
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "1")
    monkeypatch.setenv("AQUILA_PLAN_AUTO_APPROVE_MICRO", "1")
    assert plan_needs_review({"approval_status": "draft"}, micro_plan=True) is False
    assert plan_needs_review({"approval_status": "draft"}, micro_plan=False) is True
    assert plan_needs_review({"approval_status": "approved"}, micro_plan=False) is False


def test_render_plan_markdown_includes_steps():
    md = render_plan_markdown(
        {
            "user_goal": "G",
            "approach_summary": "A",
            "steps": [{"description": "step1", "step_kind": "work", "status": "pending"}],
        }
    )
    assert "step1" in md
    assert "G" in md
