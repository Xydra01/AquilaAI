"""Writing plan generation capability."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.adapters import attach_capability_ids_to_plan
from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability


class GenerateWritingPlanInput(BaseModel):
    user_request: str = Field(..., min_length=1)
    dynamic_loop: bool = True
    use_template_fallback: bool = True


def _run_generate_plan(ctx: CapabilityContext, inp: GenerateWritingPlanInput) -> CapabilityResult:
    from agent.core.plan_validator import build_fallback_writing_plan

    plan, note = build_fallback_writing_plan(
        inp.user_request,
        dynamic_loop=inp.dynamic_loop,
    )
    attach_capability_ids_to_plan(plan, mode="writing")
    return CapabilityResult.success(
        note,
        plan=plan,
        step_count=len(plan.get("steps") or []),
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.plan.generate_writing@v1",
        version="v1",
        title="Generate writing plan",
        description="Template writing plan with capability_id steps (fallback when LLM planner fails).",
        input_model=GenerateWritingPlanInput,
        handler=_run_generate_plan,
        tier="C",
        modes=frozenset({"writing"}),
    )
)
