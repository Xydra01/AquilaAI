"""Learn syllabus plan expansion and tool allowlists."""
from plan_validator import expand_learn_syllabus_plan, validate_and_tune_plan
from tool_catalog import (
    LEARN_SYLLABUS_READ_TOOLS,
    LEARN_SYLLABUS_SYNTHESIZE_TOOLS,
    allowed_tools_for_step,
    MODE_REQUIRED,
)


def test_expand_learn_syllabus_three_steps():
    plan = {
        "steps": [
            {"status": "pending", "description": "read", "step_kind": "read"},
            {"status": "pending", "description": "syn", "step_kind": "synthesize"},
            {"status": "pending", "description": "fin", "step_kind": "finalize"},
        ]
    }
    tuned, _ = validate_and_tune_plan(
        plan, "learn_syllabus_build", "build algebra course", learn_syllabus_web=False
    )
    assert len(tuned["steps"]) == 3


def test_expand_learn_syllabus_web_four_steps():
    plan = {"steps": [{"status": "pending", "description": "x", "step_kind": "read"}]}
    expanded, note = expand_learn_syllabus_plan(
        plan, "topic course", learn_syllabus_web=True
    )
    assert len(expanded["steps"]) == 4
    assert "search" in note.lower() or expanded["steps"][0].get("step_kind") == "search"


def test_learn_read_tools_allowlist():
    names = allowed_tools_for_step(
        mode="learn_syllabus_build",
        step_kind="read",
        routed=set(),
        all_names=set(LEARN_SYLLABUS_READ_TOOLS) | {"mark_objective_complete"},
        learn_syllabus_web=False,
    )
    assert "save_research_note" in names
    assert "write_syllabus_file" not in names


def test_learn_synthesize_tools():
    names = allowed_tools_for_step(
        mode="learn_syllabus_build",
        step_kind="synthesize",
        routed=set(),
        all_names=set(LEARN_SYLLABUS_SYNTHESIZE_TOOLS) | {"mark_objective_complete"},
    )
    assert "write_syllabus_file" in names


def test_mode_required_learn_build():
    required = MODE_REQUIRED["learn_syllabus_build"]
    assert "write_syllabus_file" in required
    assert "finalize_course" in required
