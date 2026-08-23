"""Source registry capability."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.research import SourceRegistry, is_bibliography_eligible_url


class RegisterSourcesInput(BaseModel):
    sources: list[dict] = Field(default_factory=list)


def _run_register_sources(ctx: CapabilityContext, inp: RegisterSourcesInput) -> CapabilityResult:
    registry = ctx.source_registry
    if registry is None:
        registry = SourceRegistry()
        ctx.source_registry = registry
    added = 0
    for item in inp.sources:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or not is_bibliography_eligible_url(url):
            continue
        title = str(item.get("title") or "").strip() or None
        via = str(item.get("via") or "read_webpage")
        if via not in ("auto_scrape", "read_webpage"):
            via = "read_webpage"
        if registry.register(url, title=title, via=via, step_index=ctx.step_index):
            added += 1
    return CapabilityResult.success(
        f"Registered {added} new sources ({len(registry.records)} total).",
        count=len(registry.records),
        bibliography=registry.format_bibliography_markdown(),
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.register_sources@v1",
        version="v1",
        title="Register sources",
        description="Track URLs for bibliography.",
        input_model=RegisterSourcesInput,
        handler=_run_register_sources,
        tier="A",
    )
)
