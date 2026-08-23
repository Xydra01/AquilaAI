"""Gather topic sources for syllabus build (web)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability


class GatherTopicSourcesInput(BaseModel):
    topic: str = Field(..., min_length=1)
    max_searches: int = Field(2, ge=1, le=4)
    max_pages: int = Field(3, ge=1, le=6)


def _run_gather(ctx: CapabilityContext, inp: GatherTopicSourcesInput) -> CapabilityResult:
    if ctx.offline:
        return CapabilityResult.failure(
            "offline",
            "gather_topic_sources requires online mode (learn_syllabus_web).",
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
        capability_id="cap.learn.gather_topic_sources@v1",
        version="v1",
        title="Gather course topic sources",
        description="Web search/read and append notes for syllabus research.",
        input_model=GatherTopicSourcesInput,
        handler=_run_gather,
        tier="B",
        modes=frozenset({"learn_syllabus_build"}),
    )
)
