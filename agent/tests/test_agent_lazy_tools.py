"""Agent init must stay light so packaged chat is not blocked on Chroma/MCP."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_agent_init_skips_mcp_connect_and_tool_index(tmp_agent_dirs):
    from agent.core import main as main_mod
    from agent.core import reset_agent_instances
    from agent.storage import reset_memory_cache

    reset_memory_cache()
    reset_agent_instances()

    connect = MagicMock(return_value={})
    index = MagicMock()

    with patch("agent.core.mcp_bridge.McpBridge.connect_all", connect):
        with patch("agent.storage.memory.DualMemorySystem.index_tools", index):
            agent = main_mod.Agent(instance_id="default")

    assert agent._tools_ready is False
    connect.assert_not_called()
    index.assert_not_called()
    assert agent.master_prompt


def test_ensure_tools_ready_connects_and_indexes(tmp_agent_dirs):
    from agent.core import main as main_mod
    from agent.core import reset_agent_instances
    from agent.storage import reset_memory_cache

    reset_memory_cache()
    reset_agent_instances()

    connect = MagicMock(return_value={})
    index = MagicMock()

    with patch("agent.core.mcp_bridge.McpBridge.connect_all", connect):
        with patch("agent.storage.memory.DualMemorySystem.index_tools", index):
            agent = main_mod.Agent(instance_id="default")
            agent.ensure_tools_ready()

    assert agent._tools_ready is True
    connect.assert_called_once()
    index.assert_called_once()
    assert len(agent._base_tools) > 0
    assert agent._action_schema


def test_run_chat_does_not_force_tool_ready(tmp_agent_dirs, monkeypatch):
    import importlib

    from agent.core import main as main_mod
    from agent.core import reset_agent_instances
    from agent.storage import reset_memory_cache

    reset_memory_cache()
    reset_agent_instances()

    agent = main_mod.Agent(instance_id="default")
    ensure = MagicMock(wraps=agent.ensure_tools_ready)
    agent.ensure_tools_ready = ensure

    def fake_chat(*_a, **_k):
        return {"message": {"content": "hi"}}

    monkeypatch.setattr(agent.client, "chat", fake_chat)
    gen_lock = importlib.import_module("agent.core.generation_lock")
    monkeypatch.setattr(gen_lock, "try_acquire", lambda *_a, **_k: True)
    monkeypatch.setattr(gen_lock, "release", lambda: None)

    out = agent.run_chat("hello", [], stream=False)
    assert "hi" in str(out)
    ensure.assert_not_called()
    assert agent._tools_ready is False
