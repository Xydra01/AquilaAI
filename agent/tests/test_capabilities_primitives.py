"""Unit tests for Tier A research/web capabilities."""
from unittest.mock import patch

import pytest


@pytest.fixture
def ctx(tmp_path):
    from agent.capabilities.base import CapabilityContext
    from agent.storage import DualMemorySystem

    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    return CapabilityContext(memory=mem, task_id="cap_test", user_request="Test topic")


def test_web_search_cap_offline_blocked(ctx):
    from agent.capabilities import run_capability

    ctx.offline = True
    result = run_capability("cap.web.search@v1", ctx, {"query": "test"})
    assert not result.ok
    assert result.error_code == "offline"


@patch("agent.capabilities.web.search.web_search")
def test_web_search_cap(mock_search, ctx):
    from agent.capabilities import run_capability

    mock_search.return_value = "Search Results for 'x':\n\n1. Title\nURL: http://a.com\nSnippet: hi"
    result = run_capability("cap.web.search@v1", ctx, {"query": "x", "max_results": 3})
    assert result.ok
    assert "raw_text" in result.data


@patch("agent.capabilities.research.notes.save_research_note")
def test_append_note_cap(mock_save, ctx):
    from agent.capabilities import run_capability

    mock_save.return_value = "✅ saved"
    result = run_capability(
        "cap.research.append_note@v1",
        ctx,
        {"content": "New fact about calendars."},
    )
    assert result.ok
    mock_save.assert_called_once()


def test_read_notes_empty(ctx):
    from agent.capabilities import run_capability

    result = run_capability("cap.research.read_notes@v1", ctx, {})
    assert result.ok


def test_register_sources_cap(ctx):
    from agent.capabilities import run_capability
    from agent.research import SourceRegistry

    ctx.source_registry = SourceRegistry()
    result = run_capability(
        "cap.research.register_sources@v1",
        ctx,
        {"sources": [{"url": "https://www.nasa.gov/example", "title": "NASA"}]},
    )
    assert result.ok
    assert ctx.source_registry.records
