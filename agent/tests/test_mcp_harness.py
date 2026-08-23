import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import create_aquila_mcp


def test_mcp_registers_harness_tools():
    mcp = create_aquila_mcp("test-harness")
    tools = mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    for expected in (
        "aquila_list_scenarios",
        "aquila_run_scenario",
        "aquila_evaluate_run",
        "aquila_release_generation_lock",
    ):
        assert expected in names


def test_aquila_list_scenarios_json(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))

    async def _run():
        mcp = create_aquila_mcp("test")
        content, _ = await mcp.call_tool("aquila_list_scenarios", {"mode": "code"})
        return content[0].text

    text = asyncio.run(_run())
    assert "code_smoke_file" in text


def test_aquila_release_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))

    async def _run():
        mcp = create_aquila_mcp("test")
        content, _ = await mcp.call_tool("aquila_release_generation_lock", {})
        return content[0].text

    text = asyncio.run(_run())
    assert "ok" in text


def test_aquila_run_scenario_busy(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))

    async def _run():
        mcp = create_aquila_mcp("test")
        monkeypatch.setattr("mcp_host.is_generation_busy", lambda: True)
        monkeypatch.setattr("mcp_host.busy_payload", lambda: {"status": "busy"})
        return await mcp.call_tool(
            "aquila_run_scenario",
            {"scenario_id": "code_smoke_file", "engine": "stock"},
        )

    content, _ = asyncio.run(_run())
    assert "busy" in content[0].text
