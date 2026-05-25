import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tool_library import agent_tools

@patch('tool_library.agent_tools.get_active_memory')
def test_store_fact(mock_get_memory):
    """TDD Goal: Ensure the store_fact tool successfully forwards data to the SQLite database."""
    mock_memory = MagicMock()
    mock_memory.store_fact.return_value = "✅ Fact stored."
    mock_get_memory.return_value = mock_memory

    result = agent_tools.store_fact("testing", "Aquila is awesome.")

    assert "✅" in result
    mock_memory.store_fact.assert_called_with("testing", "Aquila is awesome.")

@patch('tool_library.agent_tools.get_active_memory')
def test_query_past_experience(mock_get_memory):
    """TDD Goal: Ensure the query tool accurately hits the ChromaDB episodic memory."""
    mock_memory = MagicMock()
    mock_memory.recall_experiences.return_value = "Past task: Built a calculator."
    mock_get_memory.return_value = mock_memory

    result = agent_tools.query_past_experience("calculator")

    assert "calculator" in result
    mock_memory.recall_experiences.assert_called_with("calculator")

def test_ask_user():
    """TDD Goal: Ensure the ask_user tool routes text properly to the UI via the callback."""
    agent_tools.USER_INPUT_CALLBACK = lambda q: "I want the blue theme."
    
    result = agent_tools.ask_user("Which color theme do you want?")
    assert result == "I want the blue theme."
    
    agent_tools.USER_INPUT_CALLBACK = None
    result = agent_tools.ask_user("Are you there?")
    assert "❌ SYSTEM ERROR" in result