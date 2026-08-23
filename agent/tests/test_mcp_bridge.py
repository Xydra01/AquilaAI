import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    McpBridge,
    McpServerConfig,
    mcp_tool_id,
    parse_mcp_tool_id,
    merge_tools_with_mcp,
)


def test_mcp_tool_id_roundtrip():
    tid = mcp_tool_id("MongoDB", "find")
    assert tid.startswith("mcp__")
    parsed = parse_mcp_tool_id(tid)
    assert parsed == ("MongoDB", "find")


def test_disabled_server_lists_no_tools():
    bridge = McpBridge(
        [{"name": "off", "enabled": False, "command": "echo", "transport": "stdio"}]
    )
    bridge.connect_all()
    assert bridge.list_tool_names() == []


def test_merge_tools_with_mcp_empty():
    base = {"read_file": {"func": lambda: None, "description": "read"}}
    merged = merge_tools_with_mcp(base, McpBridge([]))
    assert "read_file" in merged


def test_mcp_server_config_from_dict():
    cfg = McpServerConfig.from_dict(
        {
            "name": "remote",
            "transport": "sse",
            "url": "http://127.0.0.1:9999/sse",
            "enabled": True,
        }
    )
    assert cfg.transport == "sse"
    assert cfg.url.startswith("http")


def test_call_tool_without_connection():
    bridge = McpBridge([McpServerConfig(name="x", enabled=True, command="")])
    bridge.connect_all()
    out = bridge.call_tool("x", "ping", {})
    assert "not connected" in out.lower() or "requires command" in out.lower()


def test_build_tool_registry_empty_when_no_healthy_servers():
    bridge = McpBridge([McpServerConfig(name="bad", enabled=True, command="")])
    bridge.connect_all()
    assert bridge.build_tool_registry() == {}
