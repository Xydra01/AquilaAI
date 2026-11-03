"""Tests for Phase 1 code agent tool loop."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.core.code_agent import run_tool_session


@patch("agent.core.code_agent._execute_tool")
def test_run_tool_session_completes_on_final_report(mock_exec):
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
            out = run_tool_session(agent, user_request="test", task_name="t1")

    metrics = getattr(agent, "_last_code_session_metrics", {})
    assert metrics.get("completed") is True
    assert "Finished" in out or "ok" in out


@patch("agent.core.code_agent._execute_tool")
def test_run_tool_session_blocks_third_write_on_same_path(mock_exec, monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_SESSION_LOG", "0")
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "0")
    mock_exec.return_value = "✅ written"

    agent = MagicMock()
    agent.instance_id = "default"
    agent.memory = MagicMock()

    turns = [
        {
            "reasoning": "w1",
            "tools": [
                {"name": "write_file", "arguments": {"path": "habit.py", "content": "v1"}},
            ],
        },
        {
            "reasoning": "w2",
            "tools": [
                {"name": "write_file", "arguments": {"path": "habit.py", "content": "v2"}},
            ],
        },
        {
            "reasoning": "w3",
            "tools": [
                {"name": "write_file", "arguments": {"path": "habit.py", "content": "v3"}},
            ],
        },
    ]
    turn_iter = iter(turns)

    def _parse(*_a, **_k):
        try:
            return next(turn_iter)
        except StopIteration:
            return {"reasoning": "done", "final_report": "stop", "tools": []}

    with patch("agent.core.code_agent._parse_tool_turn", side_effect=_parse):
        with patch("agent.core.code_agent._max_turns", return_value=5):
            run_tool_session(agent, user_request="habit", task_name="repeat")

    assert mock_exec.call_count == 2
    metrics = getattr(agent, "_last_code_session_metrics", {})
    assert metrics.get("repeat_blocks", 0) >= 1


def test_heal_tool_action_maps_capabilities():
    from agent.core.code_agent import _heal_tool_action

    parsed = _heal_tool_action({
        "reasoning": "create",
        "capabilities": [{
            "id": "cap.dev.create_file@v1",
            "arguments": {"file_path": "habit.py", "content": "x"},
        }],
    })
    assert parsed["tools"][0]["name"] == "write_file"
    assert parsed["tools"][0]["arguments"]["path"] == "habit.py"


@patch("agent.core.code_agent._execute_tool")
def test_run_tool_session_tracks_parse_failures(mock_exec, monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_SESSION_LOG", "0")
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "0")
    agent = MagicMock()
    agent.instance_id = "default"
    agent.memory = MagicMock()
    agent.client.chat.return_value = {"message": {"content": "bad"}}

    with patch("agent.core.code_agent._parse_tool_turn", return_value={}):
        with patch("agent.core.code_agent._max_turns", return_value=2):
            run_tool_session(agent, user_request="test", task_name="parse_test")

    metrics = getattr(agent, "_last_code_session_metrics", {})
    assert metrics.get("parse_failures", 0) >= 1


@patch("agent.core.code_agent._execute_tool")
def test_run_tool_session_injects_auto_context_after_grep(mock_exec, monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_SESSION_LOG", "0")
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "0")
    monkeypatch.setenv("AQUILA_CODE_AUTO_CONTEXT", "1")

    grep_out = "[OK] 2 match(es)\nfoo.py:5: def bar():\nfoo.py:10: return bar"
    mock_exec.return_value = grep_out

    agent = MagicMock()
    agent.instance_id = "default"
    agent.memory = MagicMock()

    turns = [
        {
            "reasoning": "grep",
            "tools": [{"name": "grep", "arguments": {"pattern": "bar", "path": "."}}],
        },
        {
            "reasoning": "done",
            "final_report": "Found bar.",
            "tools": [],
        },
    ]
    turn_iter = iter(turns)

    def _parse(*_a, **_k):
        return next(turn_iter)

    with patch("agent.core.code_agent._parse_tool_turn", side_effect=_parse):
        with patch("agent.core.code_agent._max_turns", return_value=5):
            with patch(
                "agent.core.code_agent.maybe_auto_context_after_grep",
                return_value="Auto-context:\n5|def bar():",
            ):
                run_tool_session(agent, user_request="find bar", task_name="auto_ctx")

    assert agent.client.chat.call_count >= 2
    second_call_messages = agent.client.chat.call_args_list[1][0][0]
    user_contents = [m["content"] for m in second_call_messages if m.get("role") == "user"]
    assert any("Auto-context" in str(c) for c in user_contents)