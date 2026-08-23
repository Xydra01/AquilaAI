import pytest
from agent.core.loop_coach import LoopCoach

def test_repetition_break_hint():
    coach = LoopCoach(mode="writing")
    
    pending_milestones = ["draft"]
    valid_tools = frozenset({"append_project_markdown", "write_section", "read_all_research_notes"})
    
    hint = coach.repetition_break_hint(pending_milestones, valid_tools)
    
    assert "You have repeated the same output 3 times" in hint
    assert "Pending milestones: draft" in hint
    # append_project_markdown should be in the suggested hints for 'draft' milestone
    assert "append_project_markdown" in hint
    assert "write_section" in hint
    # read_all_research_notes shouldn't be suggested for 'draft', but it should be in valid tools
    assert "Valid tools:" in hint
    assert "read_all_research_notes" in hint

def test_repetition_break_hint_no_matching_tools():
    coach = LoopCoach(mode="writing")
    
    pending_milestones = ["deliver"]
    valid_tools = frozenset({"read_all_research_notes"}) # no delivery tools
    
    hint = coach.repetition_break_hint(pending_milestones, valid_tools)
    
    assert "Pending milestones: deliver" in hint
    assert "To satisfy 'deliver'" not in hint # shouldn't suggest tools it doesn't have
    assert "Valid tools: read_all_research_notes" in hint
