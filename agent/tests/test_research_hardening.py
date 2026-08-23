"""Regression tests for research run hardening (query, scrape, guards)."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import resolve_context_profile
from agent.core import LoopCoach
from agent.core import LoopEngine
from agent.coding import PathVisitRegistry
from agent.policies import ResearchPolicy
from agent.research import (
    GITHUB_SCRAPE_CHAR_CAP,
    MIN_SUB_BUDGET_PER_SEARCH,
    SourceRegistry,
    enrich_search_result,
    extract_titles_by_url,
    is_bibliography_eligible_url,
    pick_urls_to_scrape,
    scrape_char_cap_for_url,
    score_url,
)
from agent.research import clean_research_query, low_quality_results_note


def test_clean_research_query_strips_lightweight_for_docker():
    cleaned, note = clean_research_query(
        "lightweight docker imap caldav privacy security compose"
    )
    assert "lightweight" not in cleaned.lower()
    assert "privacy" not in cleaned.lower()
    assert note is not None
    assert "docker" in cleaned.lower()


def test_score_url_penalizes_cambridge_dictionary():
    cambridge = score_url("https://dictionary.cambridge.org/lightweight")
    github = score_url("https://github.com/example/repo")
    assert cambridge < github


def test_bibliography_rejects_dictionary_hosts():
    assert not is_bibliography_eligible_url("https://www.merriam-webster.com/lightweight")
    assert is_bibliography_eligible_url("https://github.com/org/repo")


def test_enrich_skips_definition_title_urls():
    text = (
        "Search Results for 'lightweight':\n\n"
        "1. Lightweight definition\n"
        "URL: https://dictionary.cambridge.org/lightweight\n"
        "Snippet: meaning\n\n"
        "2. Dovecot\nURL: https://github.com/dovecot/core\n"
    )
    titles = extract_titles_by_url(text)
    picks = pick_urls_to_scrape(
        [
            "https://dictionary.cambridge.org/lightweight",
            "https://github.com/dovecot/core",
        ],
        set(),
        2,
        titles,
    )
    urls = [p[0] for p in picks]
    assert all("cambridge" not in u for u in urls)
    assert any("github.com" in u for u in urls)


def test_save_research_note_heal_without_task_name():
    args, note = LoopEngine._normalize_research_tool_args(
        "save_research_note",
        {"topic": "x", "gathered_data": "fact"},
        "taskaquila_1780273651",
    )
    assert "task_name" not in args
    assert note == "fact"


def test_strip_scratchpad_sentinel_from_gathered_data():
    raw = "No research notes found for this task.\n- Iran event 2024"
    cleaned = LoopEngine._strip_scratchpad_sentinel(raw)
    assert "No research notes found" not in cleaned
    assert "Iran event" in cleaned


def test_heal_topic_fact_into_gathered_data():
    args = LoopEngine._heal_save_research_note_args(
        {"topic": "Lebanon", "fact": "ceasefire timeline"}
    )
    assert "gathered_data" in args
    assert "Lebanon" in args["gathered_data"] or "ceasefire" in args["gathered_data"]
    assert "topic" not in args


def test_scratchpad_quality_blocks_sentinel():
    coach = LoopCoach(mode="research")
    block = coach.scratchpad_quality_block("No research notes found for this task.")
    assert block is not None
    assert "placeholder" in block.lower()


def test_research_policy_blocks_second_web_search():
    policy = ResearchPolicy(mode="research", step_kind="search")
    assert policy.block_message("web_search", web_search_done_this_turn=0) is None
    msg = policy.block_message("web_search", web_search_done_this_turn=1)
    assert msg is not None
    assert "One web_search" in msg


def test_path_registry_blocks_repeated_failures():
    reg = PathVisitRegistry()
    path = "/Aquila/docker-compose.yml"
    reg.record_path_failure("read_file_region", path)
    assert reg.check_path_failure("read_file_region", path) is None
    reg.record_path_failure("read_file_region", path)
    block = reg.check_path_failure("read_file_region", path)
    assert block is not None
    assert "OS BLOCK" in block


def test_loop_coach_merge_scratchpad_appends_new_bullets():
    existing = "- Dovecot supports IMAP\n- Radicale is CalDAV"
    gathered = "- Dovecot supports IMAP\n- Mailpit catches SMTP\n- Cron uses ofelia"
    merged = LoopCoach.try_merge_scratchpad(gathered, existing)
    assert merged is not None
    assert "Mailpit" in merged
    assert merged.count("Dovecot") == 1


def test_github_scrape_char_cap():
    profile = resolve_context_profile("aquila-tq-96k")
    cap = scrape_char_cap_for_url("https://github.com/org/repo", profile)
    assert cap <= GITHUB_SCRAPE_CHAR_CAP


@patch("tool_library.web_tools.read_webpage")
def test_parallel_web_search_budget_split(mock_read):
    mock_read.return_value = "x" * 500
    profile = resolve_context_profile("aquila-tq-96k")
    budget = [24_000]
    result = (
        "1. Paper\nURL: https://arxiv.org/abs/1\n\n"
        "2. Repo\nURL: https://github.com/a/b\n"
    )
    enrich_search_result(
        result,
        set(),
        SourceRegistry(),
        profile,
        scrape_budget_remaining=budget,
        max_urls_override=1,
        budget_cap=max(MIN_SUB_BUDGET_PER_SEARCH, 24_000 // 3),
    )
    assert mock_read.call_count <= 1


def test_low_quality_dictionary_without_github():
    blob = (
        "Search Results for 'lightweight imap':\n\n"
        "1. Def\nURL: https://dictionary.cambridge.org/lightweight\n"
    )
    msg = low_quality_results_note(blob)
    assert msg is not None


def test_github_blob_404_hint():
    hint = LoopCoach.github_blob_404_hint()
    assert "blob" in hint.lower()
    assert "repo root" in hint.lower()
