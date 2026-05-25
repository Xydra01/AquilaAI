import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import format_attachment_context, Agent


def test_format_attachment_context_empty():
    assert format_attachment_context(None) == ""
    assert format_attachment_context([]) == ""


def test_format_attachment_context_includes_chunk():
    chunks = ["File content here"]
    result = format_attachment_context(chunks)
    assert "ATTACHED CONTEXT" in result
    assert "File content here" in result


def test_format_attachment_context_multiple_chunks():
    chunks = ["part one", "part two"]
    result = format_attachment_context(chunks)
    assert "part one" in result
    assert "part two" in result


def test_generate_plan_includes_attachment(monkeypatch):
    import main as main_mod

    captured = {}

    def fake_chat(messages, **kwargs):
        captured["content"] = messages[0]["content"]
        return {
            "message": {
                "content": (
                    '\n  {"status": "pending", "description": "Step 1", "max_iterations": 2}\n  ]\n}'
                )
            }
        }

    agent = main_mod.Agent()
    monkeypatch.setattr(agent.client, "chat", fake_chat)

    plan = agent.generate_plan(
        "topic", "Build app", "task", text_chunks=["SECRET_ATTACHMENT_DATA"]
    )
    assert plan  # valid JSON string returned
    assert "SECRET_ATTACHMENT_DATA" in captured["content"]
    assert "ATTACHED CONTEXT" in captured["content"]
