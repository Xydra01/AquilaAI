"""Two-phase act loop: native think pass then structured tool JSON."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopEngine
from agent.core import StepRunState


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task_file = tmp_path / "Agent-Plans" / "t.json"
    task_file.parent.mkdir(parents=True)
    state = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Search web", "status": "pending", "max_iterations": 4}],
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


def test_should_run_think_phase_respects_flag_and_retries(monkeypatch):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "1")
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "reflect")
    client = MagicMock()
    client.model_name = "aquila:latest"
    engine = _make_engine(client)
    assert engine._should_run_think_phase(0) is True
    assert engine._should_run_think_phase(1) is False
    assert engine._should_run_think_phase(0, skip_think_phase=True) is False

    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "0")
    assert engine._should_run_think_phase(0) is False


def test_format_tool_preview_uses_schema_hint_order():
    client = MagicMock()
    client.model_name = "aquila:latest"
    engine = _make_engine(client)
    engine.mode = "research"
    engine._dynamic_loop_active = True
    engine._schema_tool_names = frozenset({
        "web_search",
        "read_webpage",
        "save_research_note",
        "grep_repo",
        "write_project_markdown",
        "mark_objective_complete",
    })
    preview = engine._format_tool_preview_for_think(step_kind="work")
    assert "web_search" in preview
    assert "grep_repo" not in preview
    assert "cannot call tools" in preview.lower()


def test_summarize_think_prefers_native_trace():
    summary = LoopEngine._summarize_think_for_history(
        "deep reasoning here",
        "visible answer",
    )
    assert summary == "deep reasoning here"


@patch("loop_engine.validate_tool_arguments", return_value=(True, ""))
@patch("loop_engine.validate_tool_calls", return_value=(True, ""))
@patch("loop_engine.parse_agent_response")
def test_two_phase_calls_think_then_act(
    mock_parse,
    _mock_validate,
    _mock_args,
    monkeypatch,
    tmp_ledger,
):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "1")
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "reflect")

    calls: list[dict] = []

    def _chat(_messages, **kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("surface") == "reflect":
            return {
                "message": {
                    "content": "",
                    "thinking": "Plan: run web_search next.",
                }
            }
        return {
            "message": {
                "content": '{"reasoning":"go","tools":[]}',
            },
            "format_mode_used": "strict_schema",
        }

    client = MagicMock()
    client.chat.side_effect = _chat
    client.model_name = "aquila:latest"

    mock_parse.return_value = {"reasoning": "go", "tools": []}

    engine = _make_engine(client)

    with patch.object(engine, "_build_step_entry_messages", return_value=[]):
        with patch.object(engine, "_schema_for_step", return_value={"type": "object"}):
            engine.run(
                "t",
                "topic",
                tmp_ledger,
                cancel_check=lambda: len(calls) >= 2,
            )

    assert len(calls) >= 2
    assert calls[0]["format"] is None
    assert calls[0]["surface"] == "reflect"
    assert calls[0]["force_think_disabled"] is False
    assert calls[1]["surface"] == "act"
    assert calls[1]["force_think_disabled"] is True
    assert isinstance(calls[1]["format"], dict)


def test_run_think_phase_appends_non_episode_assistant():
    client = MagicMock()
    client.chat.return_value = {
        "message": {"content": "", "thinking": "reason deeply"},
    }
    client.model_name = "aquila:latest"
    engine = _make_engine(client)
    history: list[dict] = []
    profile = MagicMock()
    profile.in_step_token_cap = 100_000
    profile.workspace_summary_max_chars = 2000
    step_run = StepRunState(
        plan_step_index=0,
        total_steps=1,
        step_kind="research",
        max_episodes=4,
    )

    status, ledger = engine._run_think_phase(
        [{"role": "user", "content": "think"}],
        step_run=step_run,
        loop_tick=0,
        profile=profile,
        task_name="t",
        conversation_history=history,
        timeout_compress_used=False,
        ledger_text="",
    )
    assert status == "ok"
    assert "Thinking" in ledger
    assert len(history) == 1
    assert history[0].get("_think_phase") is True
    assert history[0].get("_counts_as_episode") is False


@patch("loop_engine.validate_tool_arguments", return_value=(True, ""))
@patch("loop_engine.validate_tool_calls", return_value=(True, ""))
@patch("loop_engine.parse_agent_response")
def test_two_phase_off_single_act_call(
    mock_parse,
    _mock_validate,
    _mock_args,
    monkeypatch,
    tmp_ledger,
):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "0")
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")

    calls: list[dict] = []

    def _chat(_messages, **kwargs):
        calls.append(dict(kwargs))
        return {
            "message": {"content": '{"reasoning":"go","tools":[]}'},
            "format_mode_used": "strict_schema",
        }

    client = MagicMock()
    client.chat.side_effect = _chat
    client.model_name = "aquila:latest"
    mock_parse.return_value = {"reasoning": "go", "tools": []}

    engine = _make_engine(client)
    with patch.object(engine, "_build_step_entry_messages", return_value=[]):
        with patch.object(engine, "_schema_for_step", return_value={"type": "object"}):
            engine.run(
                "t",
                "topic",
                tmp_ledger,
                cancel_check=lambda: len(calls) >= 1,
            )

    assert len(calls) == 1
    assert calls[0]["surface"] == "act"


def test_consume_think_stream_invokes_callback():
    tokens: list[str] = []

    def _gen():
        yield {"message": {"thinking": "a", "content": ""}}
        yield {"message": {"thinking": "b", "content": "answer"}}

    content, thinking = LoopEngine._consume_think_stream(
        _gen(), thinking_callback=tokens.append
    )
    assert thinking == "ab"
    assert tokens == ["a", "b"]
    assert content == "answer"
