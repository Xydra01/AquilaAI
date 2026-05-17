import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from prompts import (
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
    """TDD Goal: Ensure Research Mode strictly forbids writing tools and contains anti-spiral rules."""
    prompt = get_research_prompt("tools")
    
    assert "DATA SPIRAL PREVENTION" in prompt
    assert "strictly forbidden from using Writing Mode tools" in prompt
    assert "final_report" in prompt

def test_writing_mode_constraints():
    """TDD Goal: Ensure Writing Mode enforces the specialized drafting toolkit."""
    prompt = get_writing_prompt("tools")
    
    assert "strictly forbidden from using standard coding tools like `write_file`" in prompt
    assert "init_document" in prompt
    assert "write_section" in prompt
    assert "DATA SPIRAL PREVENTION" in prompt

def test_chat_mode_constraints():
    """TDD Goal: Ensure Chat Mode receives memory injections but strictly avoids JSON formatting."""
    mock_facts = "The sky is blue."
    mock_episodic = "Yesterday, I wrote a python script."
    
    prompt = get_chat_prompt(mock_facts, mock_episodic)
    
    assert mock_facts in prompt
    assert mock_episodic in prompt
    
    assert MODES_ROSTER in prompt
    
    assert "DO NOT output JSON" in prompt