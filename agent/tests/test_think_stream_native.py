"""Native stream parsing edge cases (mocked HTTP)."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import OllamaClient, _ThinkStreamFilter


def test_extract_trailing_answer_after_think_tag():
    open_tag = "<" + "think" + ">"
    close_tag = "<" + "/" + "think" + ">"
    text = open_tag + "reasoning here" + close_tag + "The answer is 4."
    assert _ThinkStreamFilter.extract_trailing_answer(text) == "The answer is 4."


def test_split_inline_thinking():
    open_tag = "<" + "think" + ">"
    close_tag = "<" + "/" + "think" + ">"
    raw = f"{open_tag}plan step one{close_tag}\n\nThe answer is 42."
    thinking, answer = _ThinkStreamFilter.split_inline_thinking(raw)
    assert "plan step one" in thinking
    assert "42" in answer


def test_extract_trailing_answer_from_plain_thinking():
    text = (
        "Thinking Process:\n"
        "...\n"
        "But the user's instruction is to reply with exactly: pong.\n"
        "So I need to output \"pong\"."
    )
    assert _ThinkStreamFilter.extract_trailing_answer(text) == "pong"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_stream_kill_switch_counts_thinking_tokens(mock_post, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila"}]}
    )
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"message": {"thinking": "still thinking..."}}).encode(),
        b"",
    ]
    mock_post.return_value = mock_response

    clock = {"n": 0}

    def fake_time():
        clock["n"] += 1
        # Deterministic stall: each time() call advances by 100s so
        # the subsequent no-progress check triggers quickly.
        return float(clock["n"] * 100)

    with patch("main.console.log_filename", None), patch(
        "main.console.print"
    ), patch("main.time.time", side_effect=fake_time):
        client = OllamaClient()
        chunks = list(
            client.chat(
                [{"role": "user", "content": "Hi"}],
                stream=True,
                timeout=50,
                surface="chat",
            )
        )

    assert any("forcibly severed" in (c.get("message", {}).get("content") or "") for c in chunks)
