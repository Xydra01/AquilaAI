"""Gather lore for persona build: web search + notes."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability


class GatherLoreInput(BaseModel):
    topic: str = Field(..., min_length=1)
    max_searches: int = Field(2, ge=1, le=4)
    max_pages: int = Field(3, ge=1, le=6)


def _run_gather_lore(ctx: CapabilityContext, inp: GatherLoreInput) -> CapabilityResult:
    if ctx.offline:
        return CapabilityResult.failure(
            "offline",
            "gather_lore requires online mode (persona_research_lore).",
        )
    return run_capability(
        "cap.research.gather_web_sources@v1",
        ctx,
        {
            "topic": inp.topic,
            "max_searches": inp.max_searches,
            "max_pages": inp.max_pages,
            "offline": False,
        },
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.persona.gather_lore@v1",
        version="v1",
        title="Gather persona lore",
        description="Search and read web lore, append scratchpad notes for persona build.",
        input_model=GatherLoreInput,
        handler=_run_gather_lore,
        tier="B",
        modes=frozenset({"character_build"}),
    )
)
