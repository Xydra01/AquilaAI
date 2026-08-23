"""Learn syllabus plan expansion and tool allowlists."""
from agent.core import expand_learn_syllabus_plan, validate_and_tune_plan
from agent.policies import (
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





def test_mode_required_learn_build():
    required = MODE_REQUIRED["learn_syllabus_build"]
    assert "write_syllabus_file" in required
    assert "finalize_course" in required
