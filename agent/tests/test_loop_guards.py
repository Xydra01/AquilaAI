import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    MAX_TOOLS_PER_TURN,
    get_executable_tools,
    validate_tool_calls,
    parse_agent_response,
    ToolExecutor,
    build_strict_schema,
)


def test_validate_rejects_tool_name_alias():
    ok, err = validate_tool_calls([
        {"tool_name": "write_file", "arguments": {"file_path": "x", "content": "y"}},
    ])
    assert ok is False
    assert "illegal keys" in err or "missing required key 'name'" in err


def test_validate_accepts_correct_shape():
    ok, err = validate_tool_calls([
        {"name": "list_directory", "arguments": {"path": "."}},
    ])
    assert ok is True
    assert err == ""


def test_schema_tool_items_use_name_enum():
    schema = build_strict_schema(get_executable_tools())
    items = schema["properties"]["tools"]["items"]
    assert "enum" in items["properties"]["name"]
    assert "write_file" in items["properties"]["name"]["enum"]


def test_index_codebase_excluded_from_executable_tools():
    tools = get_executable_tools()
    assert "_index_codebase" not in tools


def test_max_tools_constant():
    assert MAX_TOOLS_PER_TURN == 6


def test_parse_empty_returns_dict():
    from main import console

    console.log_filename = None
    assert parse_agent_response("not json at all") == {}
    parsed = parse_agent_response('{"reasoning":"x","tools":[]}')
    assert isinstance(parsed, dict)
    assert "tools" in parsed


def test_executor_coerces_int_args(tmp_path):
    f = tmp_path / "nums.txt"
    f.write_text("1\n2\n3\n", encoding="utf-8")

    executor = ToolExecutor()
    results = executor.execute([
        {
            "name": "read_file_lines",
            "arguments": {"file_path": str(f), "start_line": "1", "end_line": "2"},
        }
    ])
    assert "❌ Error" not in results[0]
    assert "1:" in results[0] or "Lines" in results[0]


def test_tool_calls_slice_respects_max():
    """Unit check mirroring run_unified_task truncation behavior."""
    tool_calls = [{"name": f"tool_{i}", "arguments": {}} for i in range(10)]
    if len(tool_calls) > MAX_TOOLS_PER_TURN:
        tool_calls = tool_calls[:MAX_TOOLS_PER_TURN]
    assert len(tool_calls) == MAX_TOOLS_PER_TURN
