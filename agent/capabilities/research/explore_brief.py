"""Optional pre-plan explore brief capability."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability


class ExploreBriefInput(BaseModel):
    user_request: str = Field(..., min_length=1)
    mode: str = Field("research")


def _run_explore_brief(ctx: CapabilityContext, inp: ExploreBriefInput) -> CapabilityResult:
    try:
        from agent.core.explore_agent import run_brief
        from agent.core.main import get_executable_tools
        from agent.core.main import ToolExecutor
    except ImportError:
        return CapabilityResult.failure("unavailable", "explore_agent not available.")

    if ctx.client is None:
        return CapabilityResult.failure("no_client", "LLM client required for explore brief.")

    executor = ToolExecutor()
    brief = run_brief(
        client=ctx.client,
        executor=executor,
        user_request=inp.user_request,
        mode=inp.mode,
        instance_id=ctx.instance_id or "default",
        memory=ctx.memory,
    )
    if brief is None:
        return CapabilityResult.failure("brief_failed", "Explore brief returned no result.")
    md = brief.to_markdown()
    return CapabilityResult.success(
        "Explore brief generated.",
        markdown=md,
        relevant_paths=brief.relevant_paths,
        hypotheses=brief.hypotheses,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.explore_brief@v1",
        version="v1",
        title="Explore brief",
        description="Pre-plan reconnaissance brief when AQUILA_EXPLORE_BRIEF=1.",
        input_model=ExploreBriefInput,
        handler=_run_explore_brief,
        tier="D",
    )
)
