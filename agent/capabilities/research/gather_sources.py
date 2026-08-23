"""Composite: search + read + register + note."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.policies import get_context_profile
from agent.research import (
    SourceRegistry,
    enrich_search_result,
    extract_titles_by_url,
    extract_urls_from_search_result,
    normalize_url,
    pick_urls_to_scrape,
    scrape_char_cap_for_url,
)
from agent.tool_library.web_tools import read_webpage, web_search


class GatherWebSourcesInput(BaseModel):
    topic: str = Field(..., min_length=1)
    max_searches: int = Field(2, ge=1, le=4)
    max_pages: int = Field(3, ge=1, le=6)
    scrape_char_cap: int | None = Field(None, ge=2000)
    offline: bool = False


def _run_gather(ctx: CapabilityContext, inp: GatherWebSourcesInput) -> CapabilityResult:
    if inp.offline or ctx.offline:
        return CapabilityResult.failure("offline", "gather_web_sources requires online mode.")
    if ctx.cancel_check and ctx.cancel_check():
        return CapabilityResult.failure("cancelled", "Run cancelled.")

    registry = ctx.source_registry or SourceRegistry()
    ctx.source_registry = registry
    profile = get_context_profile()
    scrape_seen: set[str] = set()
    notes_parts: list[str] = []
    searches_done = 0
    pages_read = 0

    query = inp.topic.strip()
    for _ in range(inp.max_searches):
        if ctx.cancel_check and ctx.cancel_check():
            break
        raw_search = web_search(query, max_results=5)
        searches_done += 1
        enriched = enrich_search_result(
            raw_search,
            scrape_seen,
            registry,
            step_index=ctx.step_index,
            max_urls_override=min(2, inp.max_pages),
        )
        notes_parts.append(f"## Search: {query}\n{enriched or raw_search}")

        titles = extract_titles_by_url(raw_search)
        urls = extract_urls_from_search_result(raw_search)
        ranked = pick_urls_to_scrape(urls, scrape_seen, inp.max_pages, titles=titles)
        for url, _score in ranked:
            if pages_read >= inp.max_pages:
                break
            if ctx.cancel_check and ctx.cancel_check():
                break
            cap = inp.scrape_char_cap or scrape_char_cap_for_url(url, profile)
            page_text = read_webpage(url, max_chars=cap)
            pages_read += 1
            scrape_seen.add(url)
            registry.register(
                url,
                title=titles.get(normalize_url(url)),
                via="read_webpage",
                step_index=ctx.step_index,
            )
            snippet = (page_text or "")[:4000]
            notes_parts.append(f"### Source: {url}\n{snippet}")

    if notes_parts:
        combined = "\n\n".join(notes_parts)
        note_result = run_capability(
            "cap.research.append_note@v1",
            ctx,
            {"content": combined},
        )
        if not note_result.ok:
            return note_result

    return CapabilityResult.success(
        f"Gathered {searches_done} search(es), {pages_read} page(s), "
        f"{len(registry.records)} source(s) registered.",
        searches=searches_done,
        pages=pages_read,
        sources=len(registry.records),
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.gather_web_sources@v1",
        version="v1",
        title="Gather web sources",
        description="Search, rank URLs, read top pages, register sources, append notes.",
        input_model=GatherWebSourcesInput,
        handler=_run_gather,
        tier="B",
    )
)
