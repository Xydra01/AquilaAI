"""Unit tests for Chat Mode light web research."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import resolve_context_profile
from agent.research import (
    LightResearchConfig,
    build_light_research_context,
    extract_urls_from_text,
    load_light_research_config,
)


@pytest.fixture
def scrape_profile(monkeypatch):
    monkeypatch.setenv("AQUILA_AUTO_SCRAPE", "1")
    return resolve_context_profile("aquila-tq-32k")


def test_load_light_research_config_defaults(monkeypatch):
    monkeypatch.delenv("AQUILA_LIGHT_RESEARCH_MAX_URLS", raising=False)
    monkeypatch.delenv("AQUILA_LIGHT_RESEARCH_USER_URL_READS", raising=False)
    monkeypatch.delenv("AQUILA_LIGHT_RESEARCH_MAX_USER_URLS", raising=False)
    cfg = load_light_research_config()
    assert cfg.max_urls == 1
    assert cfg.scrape_char_cap == 8000
    assert cfg.max_reads == 1
    assert cfg.user_url_reads == 2
    assert cfg.max_user_urls == 3
    assert cfg.max_search_queries == 2


def test_load_light_research_max_user_urls_env(monkeypatch):
    monkeypatch.setenv("AQUILA_LIGHT_RESEARCH_MAX_USER_URLS", "5")
    cfg = load_light_research_config()
    assert cfg.max_user_urls == 5


@patch("agent.research.light_research.plan_light_research")
def test_build_light_research_uses_max_user_urls_config(mock_plan, scrape_profile):
    mock_plan.return_value = MagicMock(
        notes=(),
        user_urls=(),
        skip_search=True,
        search_queries=(),
    )
    cfg = LightResearchConfig(max_user_urls=7, user_url_reads=2)
    with patch("agent.research.light_research.get_context_profile", return_value=scrape_profile):
        build_light_research_context("hello", config=cfg)
    mock_plan.assert_called_once()
    assert mock_plan.call_args.kwargs["max_user_urls"] == 7


def test_extract_urls_from_text():
    text = "See https://example.com/foo and http://test.org/bar."
    assert extract_urls_from_text(text, max_urls=2) == [
        "https://example.com/foo",
        "http://test.org/bar",
    ]


@patch("agent.research.light_research.enrich_search_result")
@patch("tool_library.web_tools.web_search")
def test_build_light_research_context_calls_enrich_with_one_url(
    mock_search, mock_enrich, scrape_profile
):
    mock_search.return_value = (
        "Search Results for 'widgets':\n\n"
        "1. Widgets\nURL: https://example.com/w\nSnippet: info\n"
    )
    mock_enrich.side_effect = lambda result, *a, **k: result + "\n\n(OS scrape stub)"

    cfg = LightResearchConfig(max_urls=1, scrape_char_cap=5000, max_reads=0)
    with patch("agent.research.light_research.get_context_profile", return_value=scrape_profile):
        out = build_light_research_context("what are widgets?", config=cfg)

    mock_search.assert_called_once()
    mock_enrich.assert_called_once()
    profile_arg = mock_enrich.call_args[0][3]
    assert profile_arg.auto_scrape_urls == 1
    assert "https://example.com/w" in out or "widgets" in out.lower()


@patch("tool_library.web_tools.read_webpage")
@patch("agent.research.light_research.enrich_search_result")
@patch("tool_library.web_tools.web_search")
def test_build_light_research_reads_url_in_message(
    mock_search, mock_enrich, mock_read, scrape_profile
):
    mock_search.return_value = "Search Results for 'x':\n\n1. A\nURL: https://a.com\n"
    mock_enrich.side_effect = lambda result, *a, **k: result
    mock_read.return_value = "Full page body"

    cfg = LightResearchConfig(max_urls=1, max_reads=0, user_url_reads=2)
    with patch("agent.research.light_research.get_context_profile", return_value=scrape_profile):
        out = build_light_research_context(
            "Summarize https://news.example.com/article", config=cfg
        )

    mock_read.assert_called_once()
    assert "https://news.example.com/article" in mock_read.call_args[0][0]
    assert "Full page body" in out


@patch("tool_library.web_tools.read_webpage")
@patch("agent.research.light_research._run_search_pass")
def test_build_light_research_link_only_skips_search(mock_search_pass, mock_read, scrape_profile):
    mock_read.return_value = "Linked doc body"
    cfg = LightResearchConfig(user_url_reads=1)
    with patch("agent.research.light_research.get_context_profile", return_value=scrape_profile):
        out = build_light_research_context(
            "https://docs.example.com/guide",
            config=cfg,
        )
    mock_search_pass.assert_not_called()
    mock_read.assert_called_once()
    assert "Linked doc body" in out


@patch("agent.research.light_research._run_search_pass")
@patch("tool_library.web_tools.read_webpage")
@patch("agent.research.light_research.enrich_search_result")
@patch("tool_library.web_tools.web_search")
def test_build_light_research_uses_derived_query_not_full_prompt(
    mock_search, mock_enrich, mock_read, mock_search_pass, scrape_profile
):
    mock_search_pass.return_value = "search block"
    mock_read.return_value = ""
    long_prompt = (
        "Background context " * 30
        + "What year did Python 3.12 release?"
    )
    cfg = LightResearchConfig(max_urls=1, max_reads=0, user_url_reads=0)
    with patch("agent.research.light_research.get_context_profile", return_value=scrape_profile):
        build_light_research_context(long_prompt, config=cfg)
    assert mock_search_pass.called
    query = mock_search_pass.call_args[0][0]
    assert "python" in query.lower()
    assert len(query.split()) <= 18


@patch("agent.research.build_light_research_context")
def test_run_light_research_chat_injects_web_block(mock_build):
    from agent.core import Agent

    mock_build.return_value = "snippet from search"
    agent = MagicMock(spec=Agent)
    agent.instance_id = "test-instance"
    agent.memory = MagicMock()
    agent.memory.get_all_facts.return_value = ""
    agent.memory.recall_experiences.return_value = ""
    agent.client = MagicMock()
    agent.client.chat.return_value = iter([])

    from agent.core import Agent as RealAgent

    RealAgent.run_light_research_chat(
        agent,
        "hello",
        chat_history=[],
        stream=True,
    )

    messages = agent.client.chat.call_args[0][0]
    assert any("WEB RESEARCH (light)" in (m.get("content") or "") for m in messages)
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "hello"


@patch("agent.research.build_light_research_context")
def test_run_light_research_chat_passes_status_cb(mock_build):
    from agent.core import Agent

    called = {"ok": False}

    def _cb(_text: str):
        called["ok"] = True

    def _fake_build(user_input: str, status_cb=None, **_kw):
        assert callable(status_cb)
        status_cb("Searching: x")
        return "snippet"

    mock_build.side_effect = _fake_build
    agent = MagicMock(spec=Agent)
    agent.instance_id = "test-instance"
    agent.memory = MagicMock()
    agent.memory.get_all_facts.return_value = ""
    agent.memory.recall_experiences.return_value = ""
    agent.client = MagicMock()
    agent.client.chat.return_value = iter([])

    from agent.core import Agent as RealAgent

    RealAgent.run_light_research_chat(
        agent,
        "hello",
        chat_history=[],
        stream=True,
        status_cb=_cb,
    )
    assert called["ok"] is True


def test_agent_worker_routes_light_research(qtbot, qapp):
    from agent import gui

    worker = gui.AgentWorker(
        task_name="lr",
        prompt="What is X?",
        mode="chat",
        light_web_research=True,
    )
    mock_agent = MagicMock()
    mock_agent.run_light_research_chat.return_value = iter(
        [{"message": {"content": "Answer"}}]
    )

    with patch("gui.get_agent", return_value=mock_agent):
        with qtbot.waitSignal(worker.finished_signal, timeout=3000):
            worker.start()

    mock_agent.run_light_research_chat.assert_called_once()
    mock_agent.run_chat.assert_not_called()
