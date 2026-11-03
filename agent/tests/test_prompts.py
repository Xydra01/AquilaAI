import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.core import (
    get_autonomous_prompt,
    get_research_prompt,
    get_writing_prompt,
    get_chat_prompt,
    MODES_ROSTER
)

def test_base_context_injection():
    """TDD Goal: Ensure all task-based modes receive the tool docs and JSON rules."""
    mock_docs = "- `fake_tool(arg)`: Does something."
    prompt = get_autonomous_prompt(mock_docs)
    
    assert mock_docs in prompt
    assert "SINGLE valid JSON object" in prompt
    assert MODES_ROSTER in prompt

def test_research_mode_constraints():
    """TDD Goal: Ensure Research Mode uses capability act contract."""
    prompt = get_research_prompt("tools")
    
    assert "DATA SPIRAL PREVENTION" in prompt
    assert "capabilities" in prompt.lower()
    assert "final_report" in prompt
    assert "tools" in prompt.lower()


def test_writing_mode_constraints():
    """TDD Goal: Ensure Writing Mode uses capability-act contract, not raw tools."""
    prompt = get_writing_prompt("tools")
    
    assert "cap.writing.draft_sections@v1" in prompt
    assert "cap.writing.finalize_deliverable@v1" in prompt
    assert "capabilities[]" in prompt
    assert "DATA SPIRAL PREVENTION" in prompt
    assert "write_section" not in prompt.split("Never invent")[0]

def test_chat_mode_constraints():
    """TDD Goal: Ensure Chat Mode receives memory injections but strictly avoids JSON formatting."""
    mock_facts = "The sky is blue."
    mock_episodic = "Yesterday, I wrote a python script."
    
    prompt = get_chat_prompt(mock_facts, mock_episodic)
    
    assert mock_facts in prompt
    assert mock_episodic in prompt
    
    assert MODES_ROSTER in prompt
    
    assert "DO NOT output JSON" in prompt
