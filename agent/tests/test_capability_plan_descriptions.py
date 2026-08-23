"""Capability-first plan description tests for character and learn modes."""
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.plan_descriptions import (
    TOOL_LEAK_TOKENS,
    capability_step_description,
    strip_planner_boilerplate,
)
from agent.core.plan_validator import (
    build_fallback_learn_plan,
    build_fallback_persona_plan,
    validate_and_tune_plan,
)


def _assert_no_tool_leak(text: str) -> None:
    lower = text.lower()
    # Capability IDs may contain tool-like segments (e.g. finalize_course in cap.learn.finalize_course@v1).
    stripped = re.sub(r"cap\.\w+\.\w+@v\d+", "", lower)
    for tok in TOOL_LEAK_TOKENS:
        assert tok not in stripped, f"tool leak {tok!r} in: {text!r}"


def test_learn_syllabus_plan_has_capability_descriptions():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {
                "description": (
                    "Ingest user course materials via save_research_note (no write_syllabus_file). "
                    "Topic: Build a syllabus. Topic: Build a syllabus. "
                    "Steps: ingest → write_syllabus_file → finalize_course."
                ),
                "step_kind": "read",
                "max_iterations": 4,
            },
            {
                "description": "read_all_research_notes then write_syllabus_file(JSON) once.",
                "step_kind": "synthesize",
                "max_iterations": 5,
            },
            {
                "description": "finalize_course then finish_task.",
                "step_kind": "finalize",
                "max_iterations": 4,
            },
        ],
    }
    tuned, _notes = validate_and_tune_plan(
        plan,
        "learn_syllabus_build",
        "4th Dimensional properties and espers",
        learn_syllabus_web=False,
    )
    assert len(tuned["steps"]) == 3
    for step in tuned["steps"]:
        desc = step["description"]
        _assert_no_tool_leak(desc)
        assert desc.count("Topic:") == 1
    assert tuned["steps"][0]["capability_id"] == "cap.learn.ingest_course_materials@v1"
    assert tuned["steps"][1]["capability_id"] == "cap.learn.write_syllabus@v1"
    assert tuned["steps"][2]["capability_id"] == "cap.learn.finalize_course@v1"
    assert tuned.get("capability_recipe") == "fn.learn.syllabus"


def test_character_build_plan_has_capability_descriptions():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {
                "description": "Ingest via save_research_note only (no write_persona_file).",
                "step_kind": "read",
                "max_iterations": 4,
            },
            {
                "description": "write_persona_file once",
                "step_kind": "synthesize",
                "max_iterations": 4,
            },
            {
                "description": "finalize_persona + finish_task",
                "step_kind": "finalize",
                "max_iterations": 4,
            },
        ],
    }
    tuned, _notes = validate_and_tune_plan(
        plan, "character_build", "Emet-Selch", persona_research_lore=False
    )
    for step in tuned["steps"]:
        _assert_no_tool_leak(step["description"])
        assert step["description"].count("Topic:") == 1
    assert tuned["steps"][0]["capability_id"] == "cap.persona.ingest_sources@v1"
    assert tuned.get("capability_recipe") == "fn.persona.build"


def test_strip_planner_boilerplate_removes_pipeline_and_duplicate_topics():
    raw = (
        "Ingest materials. Topic: Build course. Topic: Build course. "
        "Steps: ingest → write_syllabus_file → finalize_course. "
        "Do NOT use web_search unless attachments are insufficient."
    )
    cleaned = strip_planner_boilerplate(raw)
    assert "write_syllabus_file" not in cleaned
    assert "web_search" not in cleaned
    assert cleaned.count("Topic:") <= 1


def test_fallback_persona_plan_is_capability_first():
    plan, note = build_fallback_persona_plan("Horror Sans", persona_research_lore=False)
    assert "Recipe fallback" in note
    assert plan.get("planner_fallback") is True
    for step in plan["steps"]:
        _assert_no_tool_leak(step["description"])
    assert plan["steps"][0]["capability_id"] == "cap.persona.ingest_sources@v1"


def test_short_topic_strips_learn_prompt_junk():
    from agent.core.plan_descriptions import capability_step_description, short_topic_for_plan

    raw = (
        "Build a learning syllabus for course 'Secrets of the 4th Dimension and Merger'.\n"
        "Topic: Fiction Intake: files course_id=secrets-of-the-4th-dimension-and-merger "
        "Do NOT use web_search unless attachments are insufficient.\n"
        "Steps: ingest → write_syllabus_file (≥8 nodes, ≥5 sub-units) → finalize_course."
    )
    topic = short_topic_for_plan(raw)
    assert topic == "Secrets of the 4th Dimension and Merger"
    assert "web_search" not in topic
    assert "write_syllabus_file" not in topic
    desc = capability_step_description("learn_syllabus_build", "read", raw)
    assert desc.count("Topic:") == 1
    assert "Secrets of the 4th Dimension and Merger" in desc
    assert "write_syllabus_file" not in desc
    assert "web_search" not in desc


def test_fallback_learn_plan_is_capability_first():
    plan, note = build_fallback_learn_plan("Algebra 101", learn_syllabus_web=False)
    assert "Recipe fallback" in note
    for step in plan["steps"]:
        _assert_no_tool_leak(step["description"])
    assert capability_step_description(
        "learn_syllabus_build", "synthesize", "Algebra"
    ).startswith("Write syllabus JSON")
