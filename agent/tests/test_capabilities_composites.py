"""Integration tests for Tier B composite capabilities."""
from unittest.mock import patch

import pytest


@pytest.fixture
def ctx(tmp_path):
    from agent.capabilities.base import CapabilityContext
    from agent.storage import DualMemorySystem

    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    return CapabilityContext(memory=mem, task_id="composite_test", user_request="Gregorian calendar")


@patch("agent.capabilities.research.gather_sources.read_webpage")
@patch("agent.capabilities.research.gather_sources.web_search")
@patch("agent.capabilities.research.gather_sources.enrich_search_result")
def test_gather_web_sources(mock_enrich, mock_search, mock_read, ctx):
    from agent.capabilities import run_capability

    mock_search.return_value = (
        "Search Results for 'calendar':\n\n"
        "1. NASA\nURL: https://www.nasa.gov/calendar\nSnippet: info\n"
    )
    mock_enrich.side_effect = lambda r, *a, **k: r
    mock_read.return_value = "Content of https://www.nasa.gov/calendar:\n\nFacts here."
    result = run_capability(
        "cap.research.gather_web_sources@v1",
        ctx,
        {"topic": "Gregorian calendar", "max_searches": 1, "max_pages": 1},
    )
    assert result.ok
    assert result.data.get("searches", 0) >= 1


def test_ingest_offline_no_sources(ctx):
    from agent.capabilities import run_capability

    result = run_capability("cap.research.ingest_offline@v1", ctx, {"topic": "offline"})
    assert not result.ok
    assert result.error_code == "no_offline_sources"


def test_ingest_offline_journal(ctx):
    from agent.capabilities import run_capability

    ctx.journal_text = "User notes about the topic with enough detail."
    result = run_capability(
        "cap.research.ingest_offline@v1",
        ctx,
        {"topic": "offline topic"},
    )
    assert result.ok


def test_ingest_offline_text_chunks(ctx):
    from agent.capabilities import run_capability

    ctx.attachment_text_chunks = [
        "--- START FILE: generation_lock.py ---\nlock = True\n--- END FILE ---"
    ]
    result = run_capability(
        "cap.research.ingest_offline@v1",
        ctx,
        {"topic": "generation lock"},
    )
    assert result.ok
    assert result.data.get("blocks", 0) >= 1


@patch("agent.capabilities.research.synthesize.save_research_note")
def test_synthesize_notes_no_llm(mock_save, ctx):
    from agent.capabilities import run_capability

    ctx.memory.save_scratchpad_note("composite_test", "Fact one. Fact two. " * 50)
    mock_save.return_value = "✅ saved"
    result = run_capability(
        "cap.research.synthesize_notes@v1",
        ctx,
        {"topic": "test", "use_llm": False},
    )
    assert result.ok


def test_compile_report_from_notes(ctx):
    from agent.capabilities import run_capability

    body = "# Report\n\n## Summary\n\n" + ("Analysis paragraph. " * 40)
    ctx.memory.save_scratchpad_note("composite_test", body)
    result = run_capability("cap.research.compile_report@v1", ctx, {})
    assert result.ok
    assert "body" in result.data


def test_finalize_deliverable_writes_file(ctx, tmp_path, monkeypatch):
    from agent.capabilities import run_capability
    from agent.core.main import save_task_deliverable

    monkeypatch.setattr(
        "agent.core.main.agent_data_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    body = "# Final\n\n## Executive Summary\n\n" + ("Content. " * 100)
    ctx.memory.save_scratchpad_note("composite_test", body)
    ctx.offline = True
    ctx.attachment_text_chunks = ["pdf chunk"]
    result = run_capability(
        "cap.research.finalize_deliverable@v1",
        ctx,
        {"report_body": body},
    )
    assert result.ok
    assert result.data.get("path")
    assert (tmp_path / "Agent-Research" / "composite_test.md").is_file()
    assert "offline/attachment" in (result.summary or "").lower()
    assert "0 source" not in (result.summary or "").lower()
