import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import parse_agent_response

def test_perfect_json():
    raw_output = '{"reasoning": "I am thinking.", "tools": [{"name": "read_outline", "arguments": {}}]}'
    result = parse_agent_response(raw_output)
    
    assert "tools" in result
    assert result["tools"][0]["name"] == "read_outline"

def test_truncated_json_array():
    raw_output = '{"reasoning": "Time ran out", "tools": [{"name": "save_research_note", "arguments": {"gathered_data": "Found some data'
    result = parse_agent_response(raw_output)
    
    assert isinstance(result, dict)
    assert "tools" in result
    assert result["tools"][0]["name"] == "save_research_note"
    assert "Found some data" in result["tools"][0]["arguments"]["gathered_data"]

def test_markdown_codeblock_wrapper():
    raw_output = chr(96)*3 + 'json\n{"reasoning": "Testing markdown", "tools": []}\n' + chr(96)*3
    result = parse_agent_response(raw_output)
    
    assert "reasoning" in result
    assert result["reasoning"] == "Testing markdown"

def test_unescaped_quotes_in_string():
    raw_output = '{"reasoning": "Notes", "tools": [{"name": "save_research_note", "arguments": {"gathered_data": "He said \\"Hello\\" to me"}}]}'
    result = parse_agent_response(raw_output)
    
    assert isinstance(result, dict)
    assert "Hello" in result["tools"][0]["arguments"]["gathered_data"]