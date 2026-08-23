"""Live integration tests — require Ollama; model from OLLAMA_MODEL (default aquila)."""
import json
import sys
import os

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import OllamaClient, AQUILA_ACTION_SCHEMA, parse_agent_response

pytestmark = pytest.mark.live


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _ollama_available() -> bool:
    try:
        r = requests.get(f"{_ollama_base_url()}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    if not _ollama_available():
        pytest.skip(
            f"Ollama not reachable at {_ollama_base_url()} — start scripts/ollama-serve-turboquant-port.ps1"
        )


def test_live_non_streaming_shape(ollama_warmed):
    result = ollama_warmed.chat(
        [{"role": "user", "content": "Reply with exactly: pong"}],
        temperature=0.1,
        stream=False,
        timeout=90,
    )
    assert isinstance(result, dict)
    assert "message" in result
    assert isinstance(result["message"]["content"], str)
    assert len(result["message"]["content"]) > 0


def test_live_strict_json_schema(ollama_warmed):
    from agent.core import get_global_agent

    messages = [
        {"role": "system", "content": "Output JSON only with reasoning and tools array."},
        {"role": "user", "content": "List current directory using list_directory tool."},
    ]

    result = ollama_warmed.chat(
        messages,
        temperature=0.1,
        format=get_global_agent().action_schema,
        stream=False,
        timeout=120,
        surface="act",
    )
    content = result["message"]["content"]
    parsed = parse_agent_response(content)
    assert "tools" in parsed
    assert isinstance(parsed.get("tools"), list)
