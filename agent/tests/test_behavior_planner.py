import pytest
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import Agent

#MOCK LLM RESPONSES

VALID_PLAN_RESPONSE = """
    "status": "in_progress",
    "current_step_index": 0,
    "steps": [
        {"status": "pending", "description": "Step 1", "max_iterations": 2}
    ]
}"""

GARBAGE_RESPONSE_1 = "Sure! Here is the plan you asked for. I hope you like it! \n [This is not JSON]"
GARBAGE_RESPONSE_2 = chr(96)*3 + "json\n \"status\":\"broken_json\", \"steps\":[ \n" + chr(96)*3
SEVERED_RESPONSE = "*(System Note: Generation forcibly severed.)*"

@patch('main.client.chat')
def test_planner_recovers_from_bad_json(mock_chat):
    """
    TDD Goal: If the LLM hallucinates conversational text instead of JSON, 
    the OS should silently reject it and try again up to 3 times.
    """
    mock_chat.side_effect = [
        GARBAGE_RESPONSE_1,
        GARBAGE_RESPONSE_2,
        VALID_PLAN_RESPONSE
    ]
    
    agent = Agent()
    result_json = agent.generate_plan("Test Topic", "Test Request", "task")
    
    parsed_plan = json.loads(result_json)
    
    assert parsed_plan["status"] == "in_progress"
    assert len(parsed_plan["steps"]) == 1
    assert mock_chat.call_count == 3

@patch('main.client.chat')
def test_planner_fatal_exception(mock_chat):
    """
    TDD Goal: If the LLM completely fails 3 times in a row, 
    the OS must throw a fatal exception rather than writing a broken file.
    """
    mock_chat.side_effect = [
        GARBAGE_RESPONSE_1,
        GARBAGE_RESPONSE_2,
        GARBAGE_RESPONSE_1
    ]
    
    agent = Agent()
    
    with pytest.raises(Exception) as exc_info:
        agent.generate_plan("Test Topic", "Test Request", "task")
        
    assert "Fatal: LLM failed to generate a valid JSON plan after 3 attempts" in str(exc_info.value)
    assert mock_chat.call_count == 3

@patch('main.client.chat')
def test_planner_ignores_severed_responses(mock_chat):
    """
    TDD Goal: If the generation hits the 120s kill switch during planning,
    it must immediately retry.
    """
    mock_chat.side_effect = [
        SEVERED_RESPONSE,
        VALID_PLAN_RESPONSE
    ]
    
    agent = Agent()
    result_json = agent.generate_plan("Test Topic", "Test Request", "task")
    
    assert json.loads(result_json)["status"] == "in_progress"
    assert mock_chat.call_count == 2