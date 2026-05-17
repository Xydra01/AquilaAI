"""Live integration tests — require Ollama at localhost:11434 with model 'aquila'."""
import json
import sys
import os

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import OllamaClient, AQUILA_ACTION_SCHEMA, parse_agent_response

pytestmark = pytest.mark.live


def _ollama_available() -> bool:
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    if not _ollama_available():
        pytest.skip("Ollama not reachable at http://127.0.0.1:11434 — start Ollama to run live tests")


def test_live_non_streaming_shape():
    client = OllamaClient()
    result = client.chat(
        [{"role": "user", "content": "Reply with exactly: pong"}],
        temperature=0.1,
        stream=False,
        timeout=90,
    )
    assert isinstance(result, dict)
    assert "message" in result
    assert isinstance(result["message"]["content"], str)
    assert len(result["message"]["content"]) > 0


def test_live_strict_json_schema():
    client = OllamaClient()
    messages = [
        {"role": "system", "content": "Output JSON only with reasoning and tools array."},
        {"role": "user", "content": "List current directory using list_directory tool."},
        {"role": "assistant", "content": '```json\n{\n  "reasoning": "'},
    ]
    from main import get_global_agent

    result = client.chat(
        messages,
        temperature=0.1,
        format=get_global_agent().action_schema,
        stream=False,
        timeout=120,
    )
    content = result["message"]["content"]
    full = '```json\n{\n  "reasoning": "' + content
    parsed = parse_agent_response(full)
    assert "tools" in parsed
    assert isinstance(parsed.get("tools"), list)
