import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import MilestoneState, MilestoneTracker


def test_code_milestones_implement_and_tests():
    tr = MilestoneTracker()
    tr.record_tool("read_file", "ok content", mode="code")
    assert tr.state.evidence_count == 1
    tr.record_tool("replace_lines", "✅ patched", mode="code")
    assert tr.state.file_edited
    tr.record_tool("run_pytest", "3 passed", mode="code")
    assert tr.state.tests_green is True
    assert tr.should_suggest_advance("code", is_final_step=False)
    assert not tr.should_allow_finish("code", is_final_step=False)


def test_code_finish_on_final_with_report():
    tr = MilestoneTracker()
    tr.record_tool("replace_lines", "ok", mode="code")
    tr.note_final_report()
    assert tr.should_allow_finish("code", is_final_step=True, pending_final_report=True)


def test_research_one_search_one_note_not_advance_ready():
    tr = MilestoneTracker()
    tr.record_tool("web_search", "results", mode="research")
    tr.record_tool("save_research_note", "✅ saved", mode="research")
    assert not tr.should_suggest_advance_research()


def test_research_milestones_unlock_advance():
    tr = MilestoneTracker()
    tr.record_tool("web_search", "results", mode="research")
    tr.record_tool("web_search", "more", mode="research")
    tr.record_tool("read_webpage", "page text", mode="research")
    tr.record_tool("save_research_note", "✅ saved", mode="research")
    tr.record_tool("save_research_note", "✅ saved2", mode="research")
    assert tr.should_suggest_advance_research()
    assert tr.should_suggest_advance("research", is_final_step=False)


def test_research_finish_requires_evidence():
    tr = MilestoneTracker()
    tr.record_tool("save_research_note", "✅ saved", mode="research")
    assert not tr.should_allow_finish(
        "research", is_final_step=True, pending_final_report=True
    )
    tr.record_tool("read_webpage", "page content here", mode="research")
    assert tr.should_allow_finish(
        "research", is_final_step=True, pending_final_report=True
    )


def test_research_finish_on_final_step_without_prior_draft():
    """Final step allows finish_task once notes + evidence exist (no deliverable_draft yet)."""
    tr = MilestoneTracker()
    tr.record_tool("web_search", "results", mode="research")
    tr.record_tool("read_webpage", "page content here", mode="research")
    tr.record_tool("save_research_note", "✅ saved", mode="research")
    assert not tr.state.deliverable_draft
    assert tr.should_allow_finish("research", is_final_step=True)


def test_web_search_cap_in_state():
    tr = MilestoneTracker()
    for _ in range(3):
        tr.record_tool("web_search", "results", mode="research")
    assert tr.state.web_search_count == 3


def test_milestone_state_progress_line():
    st = MilestoneState(notes_saved=1, ingest_done=True)
    line = st.progress_line("research", is_final_step=False)
    assert "Milestones" in line


def test_task_mode_delegate_milestone():
    tr = MilestoneTracker()
    tr.record_tool("delegate_mode", "✅ delegated", mode="task")
    assert tr.state.delegate_done
    assert tr.should_suggest_advance("task", is_final_step=False)


def test_milestone_hints_learn_files_vs_web():
    from agent.core.loop_objectives import milestone_hints_for_mode

    files = milestone_hints_for_mode(
        "learn_syllabus_build",
        capability=True,
        learn_syllabus_web=False,
    )
    web = milestone_hints_for_mode(
        "learn_syllabus_build",
        capability=True,
        learn_syllabus_web=True,
    )
    files_ingest = " ".join(files.get("ingest", []))
    web_ingest = " ".join(web.get("ingest", []))
    assert "gather_topic_sources" not in files_ingest
    assert "ingest_course_materials" in files_ingest
    assert "gather_topic_sources" in web_ingest
    assert "generate_assessments" not in " ".join(files.get("progress", []))


def test_build_milestones_character_no_lore():
    from agent.core.loop_objectives import build_milestones_from_plan_steps

    steps = [
        {"step_kind": "read", "capability_id": "cap.persona.ingest_sources@v1"},
        {"step_kind": "synthesize", "capability_id": "cap.persona.write_initialization@v1"},
        {"step_kind": "finalize", "capability_id": "cap.persona.finalize@v1"},
    ]
    milestones = build_milestones_from_plan_steps(steps, "character_build")
    criteria = " ".join(m["success_criteria"] for m in milestones)
    assert "ingest_sources" in criteria
    assert "gather_lore" not in criteria


def test_build_milestones_character_with_lore():
    from agent.core.loop_objectives import build_milestones_from_plan_steps

    steps = [
        {"step_kind": "search", "capability_id": "cap.persona.gather_lore@v1"},
        {"step_kind": "read", "capability_id": "cap.persona.ingest_sources@v1"},
        {"step_kind": "synthesize", "capability_id": "cap.persona.write_initialization@v1"},
        {"step_kind": "finalize", "capability_id": "cap.persona.finalize@v1"},
    ]
    milestones = build_milestones_from_plan_steps(steps, "character_build")
    ingest = next(m for m in milestones if m["id"] == "ingest")
    assert "gather_lore" in ingest["success_criteria"]
    assert "ingest_sources" in ingest["success_criteria"]
