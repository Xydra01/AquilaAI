"""Live prompt contract tests against the aquila model."""
import sys
import os

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import OllamaClient, AQUILA_ACTION_SCHEMA, parse_agent_response
from prompts import get_chat_prompt

pytestmark = pytest.mark.live


def _ollama_available() -> bool:
    try:
        return requests.get("http://127.0.0.1:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    if not _ollama_available():
        pytest.skip("Ollama not reachable at http://127.0.0.1:11434")


def test_live_chat_mode_natural_language():
    client = OllamaClient()
    prompt = get_chat_prompt("No facts.", "No experiences.")
    result = client.chat(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Say hello in one short sentence."},
        ],
        temperature=0.5,
        stream=False,
        timeout=90,
    )
    text = result["message"]["content"]
    assert text.strip()
    assert not text.strip().startswith("{")


def test_live_task_mode_json_output():
    client = OllamaClient()
    messages = [
        {
            "role": "system",
            "content": "You must output strict JSON with reasoning and tools keys only.",
        },
        {"role": "user", "content": "Call list_directory on path '.'"},
        {"role": "assistant", "content": '```json\n{\n  "reasoning": "'},
    ]
    from main import get_global_agent

    result = client.chat(
        messages,
        temperature=0.2,
        format=get_global_agent().action_schema,
        stream=False,
        timeout=120,
    )
    parsed = parse_agent_response('```json\n{\n  "reasoning": "' + result["message"]["content"])
    assert isinstance(parsed.get("reasoning"), str)
    assert isinstance(parsed.get("tools"), list)
