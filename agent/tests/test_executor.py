import pytest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import ToolExecutor

#Dummy Tools for Testing
def mock_say_hello(name: str):
    return f"Hello, {name}!"

def mock_broken_tool():
    raise ValueError("Something went wrong inside the tool.")

def mock_no_return_tool():
    # Tools that do things but don't return text (like save_file)
    pass 

DUMMY_TOOLS = {
    "say_hello": {"func": mock_say_hello, "description": "Says hello"},
    "broken_tool": {"func": mock_broken_tool, "description": "Always breaks"},
    "no_return": {"func": mock_no_return_tool, "description": "Does nothing"}
}

#Tests

@pytest.fixture
def executor():
    return ToolExecutor()

@patch("main.get_executable_tools")
def test_valid_tool_execution(mock_tools, executor):
    mock_tools.return_value = DUMMY_TOOLS
    tool_calls = [{"name": "say_hello", "arguments": {"name": "Aquila"}}]
    results = executor.execute(tool_calls)
    
    assert len(results) == 1
    assert "Hello, Aquila!" in results[0]

@patch("main.get_executable_tools")
def test_missing_tool(mock_tools, executor):
    mock_tools.return_value = DUMMY_TOOLS
    tool_calls = [{"name": "hallucinated_tool", "arguments": {}}]
    results = executor.execute(tool_calls)
    
    assert len(results) == 1
    assert "Function does not exist" in results[0]

@patch("main.get_executable_tools")
def test_tool_exception_handling(mock_tools, executor):
    mock_tools.return_value = DUMMY_TOOLS
    tool_calls = [{"name": "broken_tool", "arguments": {}}]
    results = executor.execute(tool_calls)
    
    assert len(results) == 1
    assert "Error - Something went wrong inside the tool" in results[0]

@patch("main.get_executable_tools")
def test_hallucinated_arguments_filtered(mock_tools, executor):
    mock_tools.return_value = DUMMY_TOOLS
    tool_calls = [{"name": "say_hello", "arguments": {"name": "Aquila", "fake_arg": "Ignore me"}}]
    results = executor.execute(tool_calls)
    
    assert len(results) == 1
    assert "Hello, Aquila!" in results[0] 

@patch("main.get_executable_tools")
def test_tool_returns_none(mock_tools, executor):
    mock_tools.return_value = DUMMY_TOOLS
    tool_calls = [{"name": "no_return", "arguments": {}}]
    results = executor.execute(tool_calls)
    
    assert len(results) == 1
    assert "(Success)" in results[0]