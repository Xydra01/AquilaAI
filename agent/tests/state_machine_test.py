import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import initialize_json_ledger, read_json_state, advance_json_state

def test_state_machine_progression(tmp_path):
    """
    TDD Goal: Verify that the ledger correctly tracks state progression,
    increments the step index, and marks the task as completed when all steps are done.
    """
    task_file = tmp_path / "test_ledger.json"
    
    steps = ["Draft Outline", "Write Content"]
    initialize_json_ledger(str(task_file), steps)
    
    state = read_json_state(str(task_file))
    assert state["status"] == "in_progress"
    assert state["current_step_index"] == 0
    assert len(state["steps"]) == 2
    assert state["steps"][0]["status"] == "pending"
    
    advance_json_state(str(task_file), "Outline created successfully.")
    
    state = read_json_state(str(task_file))
    assert state["status"] == "in_progress"
    assert state["current_step_index"] == 1
    assert state["steps"][0]["status"] == "completed"
    assert state["steps"][0]["result"] == "Outline created successfully."
    assert state["steps"][1]["status"] == "pending"
    
    advance_json_state(str(task_file), "Final content written.")
    
    state = read_json_state(str(task_file))
    
    assert state["status"] == "completed"
    assert state["current_step_index"] == 2
    assert state["steps"][1]["status"] == "completed"
    assert state["steps"][1]["result"] == "Final content written."