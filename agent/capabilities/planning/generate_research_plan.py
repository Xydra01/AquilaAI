"""Research plan generation capability."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.adapters import attach_capability_ids_to_plan
from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability


class GenerateResearchPlanInput(BaseModel):
    user_request: str = Field(..., min_length=1)
    offline: bool = False
    explore_brief_ran: bool = False
    use_template_fallback: bool = True


def _run_generate_plan(ctx: CapabilityContext, inp: GenerateResearchPlanInput) -> CapabilityResult:
    from agent.core.plan_validator import build_fallback_research_plan

    plan, note = build_fallback_research_plan(
        inp.user_request,
        explore_brief_ran=inp.explore_brief_ran,
        offline_research=inp.offline,
    )
    attach_capability_ids_to_plan(plan, offline=inp.offline)
    return CapabilityResult.success(
        note,
        plan=plan,
        step_count=len(plan.get("steps") or []),
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.plan.generate_research@v1",
        version="v1",
        title="Generate research plan",
        description="Template research plan with capability_id steps (fallback when LLM planner fails).",
        input_model=GenerateResearchPlanInput,
        handler=_run_generate_plan,
        tier="C",
    )
)
