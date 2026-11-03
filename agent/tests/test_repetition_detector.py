import pytest
from agent.core.loop_coach import LoopCoach

def test_repetition_break_hint():
    coach = LoopCoach(mode="writing", capability_research=True)
    
    pending_milestones = ["draft"]
    valid_caps = frozenset({
        "cap.writing.init_document@v1",
        "cap.writing.draft_sections@v1",
        "read_all_research_notes",
    })
    
    hint = coach.repetition_break_hint(pending_milestones, valid_caps)
    
    assert "You have repeated the same output 3 times" in hint
    assert "Pending milestones: draft" in hint
    assert "cap.writing.draft_sections@v1" in hint
    assert "Valid capabilities:" in hint
    assert "read_all_research_notes" in hint

def test_repetition_break_hint_no_matching_tools():
    coach = LoopCoach(mode="writing")
    
    pending_milestones = ["deliver"]
    valid_tools = frozenset({"read_all_research_notes"}) # no delivery tools
    
    hint = coach.repetition_break_hint(pending_milestones, valid_tools)
    
    assert "Pending milestones: deliver" in hint
    assert "To satisfy 'deliver'" not in hint # shouldn't suggest tools it doesn't have
    assert "Valid tools: read_all_research_notes" in hint


def test_repetition_break_hint_create_file_on_existing_path():
    coach = LoopCoach(mode="code", capability_research=True)
    hint = coach.repetition_break_hint(
        [],
        frozenset({
            "cap.dev.create_file@v1",
            "cap.dev.edit_apply@v1",
            "cap.dev.read_region@v1",
            "cap.dev.run_tests@v1",
        }),
        repeat_cap_id="cap.dev.create_file@v1",
        repeat_file_path="tests/test_habit.py",
    )
    assert "edit_apply@v1" in hint
    assert "tests/test_habit.py" in hint
    assert "Do NOT call `create_file`" in hint


def test_create_file_retry_hint_second_attempt():
    hint = LoopCoach.create_file_retry_hint("tests/test_habit.py", 2, goal="habit tracker")
    assert "full file body" in hint.lower()
    assert LoopCoach.create_file_retry_hint("tests/test_habit.py", 1) == ""
