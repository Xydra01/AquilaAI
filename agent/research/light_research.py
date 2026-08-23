"""Light web research for Chat Mode: planned search, auto-scrape, user URL reads."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace

from agent.policies import ContextProfile, get_context_profile
from .light_research_plan import (
    LightResearchPlan,
    extract_urls_from_text,
    plan_light_research,
)
from .web_enrichment import SourceRegistry, enrich_search_result
from .search_config import get_search_url


@dataclass(frozen=True)
class LightResearchConfig:
    max_urls: int = 1
    scrape_char_cap: int = 8000
    max_reads: int = 1
    read_max_chars: int | None = None
    max_search_queries: int = 2
    max_query_words: int = 18
    max_user_urls: int = 3
    user_url_reads: int = 2


def load_light_research_config() -> LightResearchConfig:
    def _int(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return max(0, int(raw))
        except ValueError:
            return default

    read_cap = None
    raw_read = os.getenv("AQUILA_LIGHT_RESEARCH_READ_MAX_CHARS", "").strip()
    if raw_read.isdigit():
        read_cap = int(raw_read)

    return LightResearchConfig(
        max_urls=_int("AQUILA_LIGHT_RESEARCH_MAX_URLS", 1),
        scrape_char_cap=_int("AQUILA_LIGHT_RESEARCH_SCRAPE_CHAR_CAP", 8000),
        max_reads=_int("AQUILA_LIGHT_RESEARCH_MAX_READS", 1),
        read_max_chars=read_cap,
        max_search_queries=max(1, _int("AQUILA_LIGHT_RESEARCH_MAX_SEARCHES", 2)),
        max_query_words=max(8, _int("AQUILA_LIGHT_RESEARCH_MAX_QUERY_WORDS", 18)),
        max_user_urls=max(1, _int("AQUILA_LIGHT_RESEARCH_MAX_USER_URLS", 3)),
        user_url_reads=max(0, _int("AQUILA_LIGHT_RESEARCH_USER_URL_READS", 2)),
    )


def _light_scrape_profile(config: LightResearchConfig) -> ContextProfile:
    base = get_context_profile()
    scrape_urls = config.max_urls if config.max_urls > 0 else 1
    return replace(
        base,
        auto_scrape_urls=scrape_urls,
        scrape_char_cap=config.scrape_char_cap,
    )


def _read_user_urls(
    urls: tuple[str, ...],
    *,
    config: LightResearchConfig,
    profile: ContextProfile,
    registry: SourceRegistry,
    parts: list[str],
    status_cb=None,
) -> None:
    if not urls:
        return
    limit = config.user_url_reads if config.user_url_reads > 0 else config.max_reads
    if limit <= 0:
        parts.append(
            "⚠️ User URL(s) detected but URL reads are disabled "
            "(set AQUILA_LIGHT_RESEARCH_USER_URL_READS≥1)."
        )
        return

    from tool_library.web_tools import read_webpage

    cap = config.read_max_chars if config.read_max_chars is not None else profile.scrape_char_cap
    for idx, url in enumerate(urls[:limit], 1):
        if status_cb:
            try:
                status_cb(f"Reading link {idx}/{limit}: {url}")
            except Exception:
                pass
        try:
            page = read_webpage(url, max_chars=cap)
            parts.append(
                f"\n\n--- PAGE FROM USER URL: {url} ---\n{page}\n--- END PAGE ---"
            )
            registry.register(url, via="read_webpage")
        except Exception as exc:
            parts.append(f"\n\n(Read webpage failed for {url}: {exc})")


def _run_search_pass(
    query: str,
    *,
    config: LightResearchConfig,
    profile: ContextProfile,
    registry: SourceRegistry,
    scrape_seen: set[str],
    status_cb=None,
) -> str:
    from tool_library.web_tools import web_search

    if status_cb:
        try:
            status_cb(f"Searching: {query}")
        except Exception:
            pass
    search_result = web_search(query, max_results=5)
    if "No results found" in search_result and "Search Results" not in search_result:
        return (
            f"Search for {query!r}: no results. "
            "Ensure SearXNG is running "
            f"({get_search_url()})."
        )
    return enrich_search_result(
        search_result,
        scrape_seen,
        registry,
        profile,
        step_index=None,
        console=None,
        url_registry=None,
        scrape_budget_remaining=None,
        run_logger=None,
    ).strip()


def build_light_research_context(
    user_input: str,
    *,
    config: LightResearchConfig | None = None,
    status_cb=None,
) -> str:
    """Plan searches + reads from the user message, gather context, return markdown."""
    config = config or load_light_research_config()
    parts: list[str] = []

    # Even when auto-scrape is disabled by the context profile, allow explicit
    # calls to this helper (tests + power-users) to run a minimal search pass.

    plan: LightResearchPlan = plan_light_research(
        user_input,
        max_search_queries=config.max_search_queries,
        max_query_words=config.max_query_words,
        max_user_urls=config.max_user_urls,
    )

    for note in plan.notes:
        parts.append(f"Plan: {note}")
        if status_cb:
            try:
                status_cb(note)
            except Exception:
                pass

    profile = _light_scrape_profile(config)
    registry = SourceRegistry()
    scrape_seen: set[str] = set()

    if plan.user_urls:
        _read_user_urls(
            plan.user_urls,
            config=config,
            profile=profile,
            registry=registry,
            parts=parts,
            status_cb=status_cb,
        )

    if not plan.skip_search and plan.search_queries:
        for i, query in enumerate(plan.search_queries):
            try:
                block = _run_search_pass(
                    query,
                    config=config,
                    profile=profile,
                    registry=registry,
                    scrape_seen=scrape_seen,
                    status_cb=status_cb,
                )
                if block:
                    if len(plan.search_queries) > 1:
                        parts.append(f"\n\n--- SEARCH {i + 1}: {query} ---\n{block}")
                    else:
                        parts.append(block)
            except Exception as exc:
                parts.append(
                    f"Web search failed for {query!r} ({exc}). "
                    f"Ensure SearXNG is running ({get_search_url()})."
                )
    elif not plan.user_urls:
        return ""

    bib = registry.format_bibliography_markdown()
    if registry.records:
        parts.append(f"\n\n{bib}")

    return "\n\n".join(p for p in parts if p).strip()


# Re-export for backward compatibility
__all__ = [
    "LightResearchConfig",
    "load_light_research_config",
    "extract_urls_from_text",
    "build_light_research_context",
    "plan_light_research",
]
