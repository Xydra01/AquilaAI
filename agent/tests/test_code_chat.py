"""Tests for code_agent tool session (Phase 3: code_chat alias removed)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.core.code_agent import run_tool_session
from agent.policies.code_tool_catalog import CODE_AGENT_TOOLS


def test_code_agent_tools_include_write_and_read():
    assert "write_file" in CODE_AGENT_TOOLS
    assert "read_file" in CODE_AGENT_TOOLS


@patch("agent.core.code_agent._execute_tool")
def test_run_tool_session_completes(mock_exec):
    mock_exec.return_value = "✅ ok"
    agent = MagicMock()
    agent.instance_id = "default"
    agent.memory = MagicMock()

    turns = [
        {
            "reasoning": "write",
            "tools": [{"name": "write_file", "arguments": {"path": "a.py", "content": "x"}}],
        },
        {"reasoning": "done", "final_report": "Finished.", "tools": []},
    ]
    turn_iter = iter(turns)

    def _parse(_agent, _raw, _allowed):
        return next(turn_iter, {"reasoning": "done", "final_report": "ok", "tools": []})

    with patch("agent.core.code_agent._parse_tool_turn", side_effect=_parse):
        with patch("agent.core.code_agent._max_turns", return_value=5):
            out = run_tool_session(agent, user_request="sync test", task_name="test_sync")

    assert "Finished" in out or "ok" in out
