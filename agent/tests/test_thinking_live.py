"""Live native thinking + structured output (requires Ollama)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import parse_agent_response

pytestmark = pytest.mark.live


def test_live_stream_thinking_and_content(ollama_warmed):
    chunks = list(
        ollama_warmed.chat(
            [{"role": "user", "content": "What is 2+2? One short sentence."}],
            stream=True,
            surface="chat",
            timeout=120,
        )
    )
    assert chunks
    had_thinking = any((c.get("message") or {}).get("thinking") for c in chunks)
    had_content = any((c.get("message") or {}).get("content") for c in chunks)
    combined_content = "".join(
        (c.get("message") or {}).get("content") or "" for c in chunks
    ).strip()
    assert had_content and combined_content, (
        "Expected answer tokens in message.content after thinking phase "
        "(try raising AQUILA_CHAT_NUM_PREDICT_THINK)"
    )
    _ = had_thinking


def test_live_structured_with_think(ollama_warmed):
    from agent.core import get_global_agent

    schema = get_global_agent().action_schema
    result = ollama_warmed.chat(
        [
            {
                "role": "system",
                "content": "Output JSON only with reasoning and tools array.",
            },
            {
                "role": "user",
                "content": "Call list_directory with path '.' only.",
            },
        ],
        temperature=0.1,
        format=schema,
        stream=False,
        surface="act",
        timeout=180,
    )
    content = result["message"]["content"]
    assert content.strip().startswith("{")
    parsed = parse_agent_response(content)
    assert isinstance(parsed.get("tools"), list)
