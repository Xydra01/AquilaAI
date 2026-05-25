"""Explore brief loop with mocked Ollama client."""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from explore_agent import run_brief


def test_run_brief_full_json_response_from_ollama():
    """When Ollama returns a complete JSON object, brief must not double-merge prefill."""
    calls = {"n": 0}

    def fake_chat(messages, temperature=0.2, format=None, stream=False, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            body = (
                '{"reasoning": "Survey repo", "tools": '
                '[{"name": "read_code_outline", "arguments": {}}]}'
            )
        else:
            body = '{"reasoning": "Done", "tools": []}'
        return {"message": {"content": body}}

    client = MagicMock()
    client.chat.side_effect = fake_chat
    executor = MagicMock()
    executor.execute.return_value = ["PROJECT: demo | root: test"]

    memory = MagicMock()
    brief = run_brief(
        client=client,
        executor=executor,
        user_request="Explore this codebase",
        mode="code",
        instance_id="default",
        memory=memory,
        max_turns=3,
    )

    assert "read_code_outline" in brief.suggested_plan_sketch or brief.relevant_paths
    assert executor.execute.called
    memory.save_scratchpad_note.assert_called()


def test_run_brief_normalizes_string_tool_names():
    """Malformed tools like ["web_search"] are coerced to {name, arguments}."""
    client = MagicMock()
    client.chat.return_value = {
        "message": {
            "content": '{"reasoning": "search", "tools": ["web_search"]}',
        }
    }
    executor = MagicMock()
    executor.execute.return_value = ["Search Results for test"]
    memory = MagicMock()

    run_brief(
        client=client,
        executor=executor,
        user_request="Earth-like exoplanets",
        mode="research",
        instance_id="default",
        memory=memory,
        max_turns=1,
    )

    assert executor.execute.called
    call_args = executor.execute.call_args[0][0]
    assert call_args[0]["name"] == "web_search"
    assert call_args[0]["arguments"] == {}


def test_run_brief_retries_after_bad_json():
    calls = {"n": 0}

    def fake_chat(messages, temperature=0.2, format=None, stream=False, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"message": {"content": "not valid json at all"}}
        return {
            "message": {
                "content": '{"reasoning": "ok", "tools": [{"name": "web_search", "arguments": {"query": "x"}}]}',
            }
        }

    client = MagicMock()
    client.chat.side_effect = fake_chat
    executor = MagicMock()
    executor.execute.return_value = ["results"]
    memory = MagicMock()

    brief = run_brief(
        client=client,
        executor=executor,
        user_request="Research topic",
        mode="research",
        instance_id="default",
        memory=memory,
        max_turns=2,
    )

    assert client.chat.call_count >= 2
    assert brief.suggested_plan_sketch


def test_run_brief_retries_after_api_error_not_abort():
    """OS-level API errors should retry (no schema) instead of aborting the whole brief."""
    calls = {"n": 0}

    def fake_chat(messages, temperature=0.2, format=None, stream=False, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"message": {"content": "*(API Error: 500 Internal Server Error)*"}}
        return {
            "message": {
                "content": '{"reasoning": "ok", "tools": [{"name": "read_code_outline", "arguments": {}}]}',
            }
        }

    client = MagicMock()
    client.chat.side_effect = fake_chat
    executor = MagicMock()
    executor.execute.return_value = ["outline"]
    memory = MagicMock()

    brief = run_brief(
        client=client,
        executor=executor,
        user_request="Map the repo",
        mode="code",
        instance_id="default",
        memory=memory,
        max_turns=2,
    )

    assert client.chat.call_count >= 2
    assert executor.execute.called
    assert brief.suggested_plan_sketch


def test_run_brief_skips_fast_when_ollama_unreachable():
    client = MagicMock()
    client.chat.return_value = {
        "message": {
            "content": (
                "*(System: Ollama not reachable at http://127.0.0.1:11435. "
                "Start TurboQuant Ollama.)*"
            ),
        },
    }
    executor = MagicMock()
    memory = MagicMock()

    brief = run_brief(
        client=client,
        executor=executor,
        user_request="Map repo",
        mode="code",
        instance_id="default",
        memory=memory,
        max_turns=3,
    )

    assert client.chat.call_count == 1
    assert not executor.execute.called
    assert brief.suggested_plan_sketch
