"""Live light research (requires SearXNG + Ollama)."""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

pytestmark = pytest.mark.live


def _searxng_up() -> bool:
    try:
        r = requests.get("http://localhost:8080/search", params={"q": "test", "format": "json"}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _searxng_up(), reason="SearXNG not running on localhost:8080")
def test_build_light_research_context_live():
    from agent.research import build_light_research_context

    out = build_light_research_context("Python programming language release year")
    assert out.strip()
    assert "Search" in out or "http" in out.lower()


@pytest.mark.skipif(not _searxng_up(), reason="SearXNG not running on localhost:8080")
def test_run_light_research_chat_streams(ollama_warmed):
    from agent.core import get_agent

    agent = get_agent()
    chunks = list(
        agent.run_light_research_chat(
            "What is the current year?",
            chat_history=[],
            stream=True,
        )
    )
    text = "".join((c.get("message") or {}).get("content") or "" for c in chunks)
    assert text.strip()
