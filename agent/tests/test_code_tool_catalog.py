"""Tests for dynamic code agent tool catalog."""
from __future__ import annotations

from agent.policies.code_tool_catalog import (
    build_code_agent_json_schema,
    get_active_code_agent_tools,
)


def test_active_tools_without_semantic(monkeypatch):
    monkeypatch.delenv("AQUILA_CODE_SEMANTIC_SEARCH", raising=False)
    tools = get_active_code_agent_tools()
    assert "read_file" in tools
    assert "find_files" in tools
    assert "semantic_search" not in tools


def test_active_tools_with_semantic(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_SEMANTIC_SEARCH", "1")
    tools = get_active_code_agent_tools()
    assert "semantic_search" in tools


def test_schema_matches_active_tools(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_SEMANTIC_SEARCH", "1")
    tools = get_active_code_agent_tools()
    schema = build_code_agent_json_schema(tools)
    props = schema.get("properties", {})
    assert "tools" in props or "final_report" in props
