"""Light web research context for Chat Mode (pre-message injection)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability


class LightWebContextInput(BaseModel):
    user_input: str = Field(..., min_length=1)


def _run_light_web_context(
    ctx: CapabilityContext,
    inp: LightWebContextInput,
) -> CapabilityResult:
    from agent.research.light_research import build_light_research_context

    try:
        block = build_light_research_context(inp.user_input)
    except Exception as exc:
        return CapabilityResult.failure("light_research_failed", str(exc))
    if not (block or "").strip():
        return CapabilityResult.success(
            "No light web context needed.",
            context="",
        )
    return CapabilityResult.success(
        f"Light web context ({len(block)} chars).",
        context=block,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.light_web_context@v1",
        version="v1",
        title="Light web research context",
        description="Chat-mode planned search + scrape context block.",
        input_model=LightWebContextInput,
        handler=_run_light_web_context,
        tier="B",
    )
)
