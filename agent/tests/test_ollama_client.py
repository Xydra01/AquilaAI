import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import OllamaClient
from agent.parser import adapt_messages_openai_to_native


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_non_streaming(mock_post, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila"}]}
    )
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "model": "aquila",
        "message": {"role": "assistant", "content": "I am fully operational."},
    }
    mock_post.return_value = mock_response

    client = OllamaClient()
    assert "[" not in client.base_url
    result = client.chat([{"role": "user", "content": "Status?"}], stream=False)

    url = mock_post.call_args.args[0]
    assert url.endswith("/api/chat")
    assert mock_post.call_args.kwargs["json"]["stream"] is False
    assert isinstance(result, dict)
    assert result["message"]["content"] == "I am fully operational."


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_streaming(mock_post, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila"}]}
    )
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"message": {"content": "Hello"}}).encode(),
        json.dumps({"done": True}).encode(),
    ]
    mock_post.return_value = mock_response

    client = OllamaClient()
    chunks = list(client.chat([{"role": "user", "content": "Hi"}], stream=True))

    assert mock_post.call_args.args[0].endswith("/api/chat")
    assert chunks[0]["message"]["content"] == "Hello"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_native_think_split_stream(mock_post, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila_heretic"}]}
    )
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"message": {"thinking": "hmm"}}).encode(),
        json.dumps({"message": {"content": "Hi"}}).encode(),
        json.dumps({"done": True}).encode(),
    ]
    mock_post.return_value = mock_response

    with patch.dict(
        os.environ,
        {"OLLAMA_MODEL": "aquila_heretic", "AQUILA_ENABLE_THINK": "1"},
        clear=False,
    ):
        client = OllamaClient()
        chunks = list(
            client.chat([{"role": "user", "content": "Hi"}], stream=True)
        )

    assert chunks[0]["message"]["thinking"] == "hmm"
    assert chunks[1]["message"]["content"] == "Hi"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_num_ctx_option(mock_post, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila-tq-64k"}]}
    )
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "ok"},
    }
    mock_post.return_value = mock_response

    with patch.dict(
        os.environ,
        {"OLLAMA_MODEL": "aquila-tq-64k", "OLLAMA_NUM_CTX": "65536"},
        clear=False,
    ):
        client = OllamaClient()
        client.chat([{"role": "user", "content": "Hi"}], stream=False)

    options = mock_post.call_args.kwargs["json"]["options"]
    assert options["num_ctx"] == 65536


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_schema_fallback_chain(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})
    schema = {"type": "object", "properties": {"reasoning": {"type": "string"}}}
    fail = MagicMock()
    fail.raise_for_status.side_effect = __import__("requests").HTTPError("400")
    fail.response = MagicMock(text='{"error":"bad schema"}', status_code=400)

    ok = MagicMock()
    ok.json.return_value = {"message": {"content": '{"reasoning":"hi"}'}}

    mock_post.side_effect = [fail, fail, ok]

    client = OllamaClient()
    result = client.chat(
        [{"role": "user", "content": "Hi"}], format=schema, stream=False
    )

    assert result["message"]["content"] == '{"reasoning":"hi"}'
    assert result.get("format_mode_used") == "json_object"
    first_fmt = mock_post.call_args_list[0].kwargs["json"].get("format")
    assert isinstance(first_fmt, dict)
    assert mock_post.call_args_list[-1].kwargs["json"].get("format") == "json"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_skips_schema_when_assistant_json_prefill(mock_post, mock_get):
    """Prefill + JSON Schema → skip schema attempts; use json_object only."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})
    schema = {"type": "object", "properties": {"reasoning": {"type": "string"}}}
    ok = MagicMock()
    ok.json.return_value = {"message": {"content": '{"reasoning":"ok","tools":[]}'}}
    mock_post.return_value = ok

    client = OllamaClient()
    messages = [
        {"role": "user", "content": "Act"},
        {"role": "assistant", "content": '{\n  "reasoning": "'},
    ]
    result = client.chat(messages, format=schema, stream=False, surface="act")
    assert result.get("format_mode_used") == "json_object"
    # First (and only structured) attempt must not be a schema dict
    assert mock_post.call_count >= 1
    first_fmt = mock_post.call_args_list[0].kwargs["json"].get("format")
    assert first_fmt == "json"
    for call in mock_post.call_args_list:
        assert not isinstance(call.kwargs["json"].get("format"), dict)


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ensure_warmup_called_before_chat(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})
    warm = MagicMock(status_code=200)
    warm.json.return_value = {"message": {"content": "ok"}}
    chat = MagicMock()
    chat.json.return_value = {"message": {"content": "answer"}}
    mock_post.side_effect = [warm, chat]

    with patch.dict(os.environ, {"AQUILA_SKIP_WARMUP": "0"}, clear=False):
        client = OllamaClient()
        client._warmed = False
        result = client.chat([{"role": "user", "content": "Hi"}], stream=False)

    assert result["message"]["content"] == "answer"
    assert mock_post.call_count >= 2
    assert mock_post.call_args_list[0].args[0].endswith("/api/chat")


def test_message_adapter_images():
    msgs = adapt_messages_openai_to_native([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is this?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,abc123"},
                },
            ],
        }
    ])
    assert msgs[0]["content"] == "What is this?"
    assert msgs[0]["images"] == ["abc123"]


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_no_retry_on_connection_refused(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})
    mock_post.side_effect = __import__("requests").exceptions.ConnectionError(
        "Connection refused"
    )

    client = OllamaClient()
    result = client.chat(
        [{"role": "user", "content": "Hi"}], format={"type": "object"}, stream=False
    )

    assert mock_post.call_count == 1
    assert "not reachable" in result["message"]["content"]


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_eject_model(mock_post, mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila-tq-32k"}]}
    )
    mock_post.return_value = MagicMock(status_code=200)

    client = OllamaClient()
    client.model_name = "aquila-tq-32k"
    ok, msg = client.eject_model()

    assert ok is True
    assert "Unloaded" in msg
    assert mock_post.call_args.kwargs["json"]["keep_alive"] == 0


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_eject_all_loaded(mock_post, mock_get):
    def get_side_effect(url, **kwargs):
        resp = MagicMock(status_code=200)
        if url.endswith("/api/ps"):
            resp.json.return_value = {
                "models": [{"name": "aquila-tq-32k"}, {"name": "other:latest"}]
            }
        else:
            resp.json.return_value = {"models": []}
        return resp

    mock_get.side_effect = get_side_effect
    mock_post.return_value = MagicMock(status_code=200)

    client = OllamaClient()
    ok, msg = client.eject_model(all_loaded=True)

    assert ok is True
    assert mock_post.call_count == 2


@patch("main.console.log_filename", None)
@patch("main.console.print")
@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_plain_chat_includes_repeat_penalty(mock_post, mock_get, _print):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila-tq-32k"}]}
    )
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"message": {"content": "ok"}}).encode(),
        json.dumps({"done": True}).encode(),
    ]
    mock_post.return_value = mock_response

    with patch.dict(os.environ, {"AQUILA_SKIP_WARMUP": "1"}, clear=False):
        client = OllamaClient()
        client.model_name = "aquila-tq-32k"
        list(client.chat([{"role": "user", "content": "Hi"}], stream=True, surface="chat"))

    opts = mock_post.call_args.kwargs["json"].get("options") or {}
    assert opts.get("repeat_penalty", 0) > 1.0
    assert opts.get("repeat_last_n", 0) >= 8


@patch("main.console.log_filename", None)
@patch("main.console.print")
@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_stream_stops_on_repetitive_content(mock_post, mock_get, _print):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "aquila"}]}
    )
    line = "Title now captures essence of project\n"
    payload = "Intro.\n\n" + line * 5
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"message": {"content": payload}}).encode(),
        json.dumps({"done": True}).encode(),
    ]
    mock_post.return_value = mock_response

    with patch.dict(os.environ, {"AQUILA_SKIP_WARMUP": "1"}, clear=False):
        client = OllamaClient()
        chunks = list(
            client.chat([{"role": "user", "content": "Revise"}], stream=True, surface="chat")
        )

    text = "".join((c.get("message") or {}).get("content") or "" for c in chunks)
    assert "repetitive generation" in text.lower()
