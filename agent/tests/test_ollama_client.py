import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import OllamaClient

@patch('main.requests.Session.get')
@patch('main.requests.Session.post')
def test_ollama_client_non_streaming(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "aquila"}]})
    """TDD Goal: Ensure non-streaming requests return a clean dictionary, not a generator."""
    mock_response = MagicMock()
    # Mock exactly what Ollama returns for stream=False
    mock_response.json.return_value = {
        "model": "aquila",
        "message": {"role": "assistant", "content": "I am fully operational."},
        "choices": [{"message": {"content": "I am fully operational."}}]
    }
    mock_post.return_value = mock_response

    client = OllamaClient()
    
    # 1. Verify the base_url does not contain markdown artifacts
    assert "[" not in client.base_url
    assert "]" not in client.base_url
    
    # 2. Trigger a non-streaming chat
    result = client.chat([{"role": "user", "content": "Status?"}], stream=False)
    
    # 3. Verify requests.post was called with stream=False
    args, kwargs = mock_post.call_args
    assert kwargs["stream"] is False
    assert kwargs["json"]["stream"] is False
    
    # 4. Verify it returns the standard dictionary the OS needs
    assert isinstance(result, dict)
    assert result["message"]["content"] == "I am fully operational."

@patch('main.requests.Session.get')
@patch('main.requests.Session.post')
def test_ollama_client_streaming(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "aquila"}]})
    """TDD Goal: Ensure streaming requests yield chunks for the UI to consume."""
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        b'data: {"choices": [{"delta": {"content": "Hello"}}]}',
        b'data: [DONE]'
    ]
    mock_post.return_value = mock_response

    client = OllamaClient()
    generator = client.chat([{"role": "user", "content": "Hi"}], stream=True)
    
    # Verify requests.post was called with stream=True
    args, kwargs = mock_post.call_args
    assert kwargs["stream"] is True
    assert kwargs["json"]["stream"] is True
    
    # Pull from the generator and verify structure
    chunks = list(generator)
    assert chunks[0]["message"]["content"] == "Hello"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_num_ctx_option(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "aquila-tq-64k"}]})
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
    }
    mock_post.return_value = mock_response

    with patch.dict(os.environ, {"OLLAMA_MODEL": "aquila-tq-64k", "OLLAMA_NUM_CTX": "65536"}, clear=False):
        client = OllamaClient()
        client.chat([{"role": "user", "content": "Hi"}], stream=False)

    options = mock_post.call_args.kwargs["json"]["options"]
    assert options["num_ctx"] == 65536
    assert mock_post.call_args.kwargs["json"]["model"] == "aquila-tq-64k"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_schema_fallback_chain(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})
    """Strict json_schema failure should retry json_object then plain."""
    schema = {"type": "object", "properties": {"reasoning": {"type": "string"}}}
    fail = MagicMock()
    fail.raise_for_status.side_effect = __import__("requests").HTTPError("400")
    fail.response = MagicMock(text='{"error":"bad schema"}')

    ok = MagicMock()
    ok.json.return_value = {"choices": [{"message": {"content": '{"reasoning":"hi"}'}}]}

    # strict → shrunk strict → json_object
    mock_post.side_effect = [fail, fail, ok]

    client = OllamaClient()
    result = client.chat([{"role": "user", "content": "Hi"}], format=schema, stream=False)

    assert result["message"]["content"] == '{"reasoning":"hi"}'
    assert result.get("format_mode_used") == "json_object"
    assert mock_post.call_count >= 2
    first_fmt = mock_post.call_args_list[0].kwargs["json"].get("response_format", {})
    assert first_fmt.get("type") == "json_schema"
    last_fmt = mock_post.call_args_list[-1].kwargs["json"].get("response_format", {})
    assert last_fmt.get("type") == "json_object"


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_no_retry_on_connection_refused(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})
    mock_post.side_effect = __import__("requests").exceptions.ConnectionError(
        "Connection refused"
    )

    client = OllamaClient()
    schema = {"type": "object"}
    result = client.chat([{"role": "user", "content": "Hi"}], format=schema, stream=False)

    assert mock_post.call_count == 1
    assert "not reachable" in result["message"]["content"]


@patch("main.requests.Session.get")
@patch("main.requests.Session.post")
def test_ollama_client_eject_model(mock_post, mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "aquila-tq-32k"}]})
    mock_post.return_value = MagicMock(status_code=200)

    client = OllamaClient()
    client.model_name = "aquila-tq-32k"
    ok, msg = client.eject_model()

    assert ok is True
    assert "Unloaded" in msg
    assert mock_post.call_args.kwargs["json"] == {
        "model": "aquila-tq-32k",
        "prompt": "",
        "stream": False,
        "keep_alive": 0,
    }


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
    assert "aquila-tq-32k" in msg and "other:latest" in msg