"""Web search capability."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.tool_library.web_tools import web_search


class SearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(5, ge=1, le=10)


class SearchOutput(BaseModel):
    snippets: list[str] = Field(default_factory=list)
    raw_text: str = ""
    rewrite_note: str = ""


def _run_search(ctx: CapabilityContext, inp: SearchInput) -> CapabilityResult:
    if ctx.offline:
        return CapabilityResult.failure("offline", "Web search unavailable in offline mode.")
    if ctx.cancel_check and ctx.cancel_check():
        return CapabilityResult.failure("cancelled", "Run cancelled.")
    raw = web_search(inp.query, max_results=inp.max_results)
    snippets: list[str] = []
    for block in (raw or "").split("\n\n"):
        block = block.strip()
        if block and not block.startswith("Search Results"):
            snippets.append(block[:500])
    rewrite_note = ""
    if "Query rewritten" in raw or "rewritten" in raw.lower():
        rewrite_note = "Query was cleaned/rewritten before search."
    return CapabilityResult.success(
        f"Search returned {len(snippets)} result blocks.",
        raw_text=raw,
        snippets=snippets,
        rewrite_note=rewrite_note,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.web.search@v1",
        version="v1",
        title="Web search",
        description="Clean query, SearXNG search, low-quality hint.",
        input_model=SearchInput,
        handler=_run_search,
        tier="A",
    )
)
