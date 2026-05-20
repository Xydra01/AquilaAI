"""Live context smoke — requires Ollama + model from OLLAMA_MODEL (e.g. aquila-tq-64k)."""
import json
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import OllamaClient, parse_agent_response

pytestmark = pytest.mark.live

# ~24k chars — long prefill without burying the task (8000 * "context " ≈ 64k was unrealistic)
_PREFILL_WORD = "context "
_PREFILL_REPEATS = 3_000
_ASSISTANT_JSON_PREFIX = '```json\n{\n  "reasoning": "'


def _parse_live_schema_response(content: str) -> dict:
    """Parse tool JSON from Ollama strict-schema or Aquila continuation-style replies."""
    text = (content or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    for candidate in (
        text,
        _ASSISTANT_JSON_PREFIX + text,
        f"```json\n{text}",
    ):
        parsed = parse_agent_response(candidate)
        if isinstance(parsed.get("tools"), list):
            return parsed
    return {}


def _ollama_available() -> bool:
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        return requests.get(f"{base}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    if not _ollama_available():
        pytest.skip("Ollama not reachable — start scripts/ollama-serve-turboquant.ps1")


def test_live_large_context_pong():
    """Prefill-heavy user message; ensures high num_ctx does not OOM immediately."""
    client = OllamaClient()
    filler = "word " * 12_000
    result = client.chat(
        [{"role": "user", "content": f"{filler}\n\nReply with exactly: pong"}],
        temperature=0.1,
        stream=False,
        timeout=300,
    )
    content = result["message"]["content"].lower()
    assert "pong" in content or len(content) > 0


def test_live_strict_json_after_filler():
    """Strict JSON tool schema still parses after a large user prefill."""
    from main import get_global_agent

    client = OllamaClient()
    filler = _PREFILL_WORD * _PREFILL_REPEATS
    messages = [
        {"role": "system", "content": "Output JSON only with reasoning and tools array."},
        {
            "role": "user",
            "content": (
                filler
                + "\n\nIgnore the filler above. List directory '.' using list_directory only."
            ),
        },
    ]
    result = client.chat(
        messages,
        temperature=0.1,
        format=get_global_agent().action_schema,
        stream=False,
        timeout=300,
    )
    content = result["message"]["content"]
    parsed = _parse_live_schema_response(content)
    assert isinstance(parsed.get("tools"), list), (
        f"expected tools array; got keys={list(parsed.keys())!r} "
        f"content_preview={content[:400]!r}"
    )
