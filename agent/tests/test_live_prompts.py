"""Live prompt contract tests against the aquila model."""
import sys
import os

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import OllamaClient, AQUILA_ACTION_SCHEMA, parse_agent_response
from agent.core import get_chat_prompt

pytestmark = pytest.mark.live


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _ollama_available() -> bool:
    try:
        return requests.get(f"{_ollama_base_url()}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    if not _ollama_available():
        pytest.skip(
            f"Ollama not reachable at {_ollama_base_url()} — start scripts/ollama-serve-turboquant-port.ps1"
        )


def test_live_chat_mode_natural_language(ollama_warmed):
    prompt = get_chat_prompt("No facts.", "No experiences.")
    result = ollama_warmed.chat(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Say hello in one short sentence."},
        ],
        temperature=0.5,
        stream=False,
        timeout=90,
        surface="chat",
    )
    text = result["message"]["content"]
    assert text.strip()
    assert not text.strip().startswith("{")


def test_live_task_mode_json_output(ollama_warmed):
    messages = [
        {
            "role": "system",
            "content": "You must output strict JSON with a 'reasoning' string field and a 'tools' array.",
        },
        {"role": "user", "content": "Call list_directory on path '.' Make sure to include the reasoning field."},
    ]
    from agent.core import get_global_agent

    result = ollama_warmed.chat(
        messages,
        temperature=0.2,
        format=get_global_agent().action_schema,
        stream=False,
        timeout=120,
        surface="act",
    )
    parsed = parse_agent_response(result["message"]["content"])
    assert isinstance(parsed.get("reasoning"), str)
    assert isinstance(parsed.get("tools"), list)
