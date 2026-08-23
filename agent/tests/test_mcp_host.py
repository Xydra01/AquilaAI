import asyncio
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import create_aquila_mcp


def test_create_aquila_mcp_registers_tools():
    mcp = create_aquila_mcp("test-aquila")
    tools = mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    expected = {
        "aquila_health",
        "aquila_list_instances",
        "aquila_run_mode",
        "aquila_run_autonomous",
        "aquila_get_task_status",
        "aquila_get_task_metrics",
        "aquila_probe_throughput",
        "aquila_read_deliverable",
        "aquila_list_scenarios",
        "aquila_run_scenario",
        "aquila_evaluate_run",
        "aquila_release_generation_lock",
    }
    assert expected <= names


def test_aquila_health_json(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))

    async def _run():
        mcp = create_aquila_mcp("test")
        with patch("main.client") as mock_client:
            mock_client.probe.return_value = True
            mock_client.model_name = "aquila"
            mock_client.base_url = "http://127.0.0.1:11434"
            with patch("main.apply_runtime_settings"):
                with patch("main.get_agent"):
                    with patch("instance_runtime.apply_instance_for_run", return_value="default"):
                        return await mcp.call_tool("aquila_health", {"instance_id": ""})

    result = asyncio.run(_run())
    text = result[0][0].text
    data = json.loads(text)
    assert data["ok"] is True
    assert "ollama_reachable" in data


def test_aquila_run_mode_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))

    async def _run():
        mcp = create_aquila_mcp("test")
        monkeypatch.setattr("mcp_host.is_generation_busy", lambda: True)
        monkeypatch.setattr("mcp_host.busy_payload", lambda: {"status": "busy", "message": "locked"})
        return await mcp.call_tool(
            "aquila_run_mode",
            {"mode": "code", "objective": "hello", "context": "", "instance_id": "", "parent_task_id": ""},
        )

    result = asyncio.run(_run())
    data = json.loads(result[0][0].text)
    assert data["status"] == "busy"
