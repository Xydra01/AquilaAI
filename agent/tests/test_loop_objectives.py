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
