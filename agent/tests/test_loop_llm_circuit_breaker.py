"""LLM circuit breaker: fail fast when Ollama is unreachable."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopEngine


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task_file = tmp_path / "Agent-Plans" / "t.json"
    task_file.parent.mkdir(parents=True)
    state = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Research", "status": "pending", "max_iterations": 8}],
    }
    task_file.write_text(json.dumps(state), encoding="utf-8")
    return str(task_file)


def _make_engine(client: MagicMock) -> LoopEngine:
    return LoopEngine(
        client=client,
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="sys",
        mode="research",
        mode_label="Research",
        plan_dir="Agent-Plans",
        base_tools={"web_search": {"description": "search"}},
    )


@patch("loop_engine.validate_tool_arguments", return_value=(True, ""))
@patch("loop_engine.validate_tool_calls", return_value=(True, ""))
@patch("loop_engine.parse_agent_response")
def test_circuit_breaker_stops_after_three_think_errors(
    mock_parse,
    _mock_validate,
    _mock_args,
    monkeypatch,
    tmp_ledger,
):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "1")
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "reflect")
    monkeypatch.setenv("AQUILA_LLM_ERROR_LIMIT", "3")

    err = "*(System: Ollama not reachable at http://127.0.0.1:11434. Start ollama serve.)"
    calls = 0

    def _chat(_messages, **kwargs):
        nonlocal calls
        calls += 1
        return {"message": {"content": err, "thinking": ""}}

    client = MagicMock()
    client.chat.side_effect = _chat
    client.model_name = "aquila:latest"
    client.base_url = "http://127.0.0.1:11434"
    mock_parse.return_value = {"reasoning": "x", "tools": []}

    engine = _make_engine(client)
    with patch.object(engine, "_build_step_entry_messages", return_value=[]):
        with patch.object(engine, "_schema_for_step", return_value={"type": "object"}):
            result = engine.run("t", "topic", tmp_ledger)

    assert "🛑" in result
    assert "11434" in result
    assert calls < 20


def test_think_error_does_not_append_tool_outputs(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    client = MagicMock()
    client.chat.return_value = {
        "message": {
            "content": "*(System: Ollama not reachable at http://127.0.0.1:11434.)",
            "thinking": "",
        },
    }
    client.model_name = "aquila:latest"
    engine = _make_engine(client)
    history: list[dict] = []
    profile = MagicMock()
    profile.in_step_token_cap = 100_000
    profile.workspace_summary_max_chars = 2000
    step_run = MagicMock()
    step_run.episode_count = 0
    step_run.plan_step_index = 0
    step_run.total_steps = 1
    step_run.step_kind = "work"

    status, _ = engine._run_think_phase(
        [{"role": "user", "content": "think"}],
        step_run=step_run,
        loop_tick=0,
        profile=profile,
        task_name="t",
        conversation_history=history,
        timeout_compress_used=False,
        ledger_text="",
    )
    assert status == "error"
    assert history == []
