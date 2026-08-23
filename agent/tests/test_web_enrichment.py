"""Tests for web enrichment: scoring, scrape selection, source registry."""
from unittest.mock import patch

import pytest

from agent.policies import resolve_context_profile
from agent.research import (
    SourceRegistry,
    enrich_search_result,
    extract_urls_from_search_result,
    normalize_url,
    pick_urls_to_scrape,
    score_url,
    strip_existing_references_section,
)


def test_score_url_prefers_edu():
    assert score_url("https://mit.edu/paper") > score_url("https://reddit.com/r/test")


def test_extract_urls_from_search_result():
    text = (
        "Search Results:\n\n1. Title\n"
        "URL: https://example.com/a\n"
        "Snippet: x\n\n"
        "2. Other\nURL: https://arxiv.org/abs/123\n"
    )
    urls = extract_urls_from_search_result(text)
    assert urls == ["https://example.com/a", "https://arxiv.org/abs/123"]


def test_pick_urls_skips_seen_and_ranks():
    urls = [
        "https://example.org/x",
        "https://stanford.edu/y",
        "https://github.com/z",
    ]
    seen = {normalize_url("https://github.com/z")}
    picks = pick_urls_to_scrape(urls, seen, 2)
    assert len(picks) == 2
    assert picks[0][0] == "https://stanford.edu/y"


def test_pick_urls_skips_dictionary():
    urls = [
        "https://dictionary.cambridge.org/lightweight",
        "https://hub.docker.com/r/linuxserver/radicale",
    ]
    titles = {
        normalize_url("https://dictionary.cambridge.org/lightweight"): "Lightweight definition"
    }
    picks = pick_urls_to_scrape(urls, set(), 2, titles)
    assert len(picks) == 1
    assert "hub.docker.com" in picks[0][0]


def test_source_registry_dedupes_and_orders():
    reg = SourceRegistry()
    assert reg.register("https://Example.org/a/", title="A", via="auto_scrape")
    assert not reg.register("https://example.org/a", via="read_webpage")
    assert reg.register("https://arxiv.org/abs/123", via="read_webpage")
    assert len(reg.records) == 2
    bib = reg.format_bibliography_markdown()
    assert "## References" in bib
    assert "[A]" in bib
    assert "arxiv.org" in bib


def test_source_registry_skips_junk_urls():
    reg = SourceRegistry()
    assert not reg.register("https://www.chegg.com/homework")
    assert not reg.register("https://dictionary.cambridge.org/x")
    assert reg.register("https://github.com/org/repo")
    assert len(reg.records) == 1


def test_strip_existing_references_section():
    body = "# Report\n\nFindings here.\n\n## References\n\n1. old"
    assert "## References" not in strip_existing_references_section(body)
    assert "Findings here." in strip_existing_references_section(body)


@patch("tool_library.web_tools.read_webpage")
def test_enrich_search_result_appends_scrape(mock_read, monkeypatch):
    monkeypatch.setenv("AQUILA_AUTO_SCRAPE", "1")
    mock_read.return_value = "Page body text"
    profile = resolve_context_profile("aquila-tq-32k")
    seen: set[str] = set()
    reg = SourceRegistry()
    result = (
        "Search Results for 'test':\n\n"
        "1. Paper\nURL: https://arxiv.org/abs/1\nSnippet: s\n"
    )
    out = enrich_search_result(result, seen, reg, profile, console=None)
    assert "AUTO-SCRAPED" in out
    assert "Page body text" in out
    assert len(reg.records) == 1
    mock_read.assert_called_once()


@patch("tool_library.web_tools.read_webpage")
def test_enrich_respects_tier_url_count(mock_read, monkeypatch):
    monkeypatch.setenv("AQUILA_AUTO_SCRAPE", "1")
    mock_read.return_value = "content"
    monkeypatch.setenv("AQUILA_CONTEXT_TIER", "max")
    profile = resolve_context_profile("aquila-tq-96k")
    seen: set[str] = set()
    result = (
        "1. a\nURL: https://a.edu/1\n\n"
        "2. b\nURL: https://b.edu/2\n\n"
        "3. c\nURL: https://c.edu/3\n\n"
        "4. d\nURL: https://d.edu/4\n"
    )
    enrich_search_result(result, seen, None, profile, console=None)
    assert mock_read.call_count == 3
