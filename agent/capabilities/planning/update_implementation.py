"""Living implementation plan capabilities (read / update checklist)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability

_LIVING_MODES = frozenset({
    "code",
    "writing",
    "research",
    "learn_syllabus_build",
    "character_build",
})


class ReadImplementationInput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class UpdateChecklistInput(BaseModel):
    item_ids: list[str] = Field(
        default_factory=list,
        description="Checklist item ids to update (from implementation plan).",
    )
    status: str = Field(
        "done",
        description="New status: pending | done | skipped.",
    )
    texts: list[str] = Field(
        default_factory=list,
        description="Optional fuzzy match against checklist item text.",
    )
    summary_patch: str = Field(
        "",
        description="Optional replacement for implementation.summary.",
    )


def _load_plan(ctx: CapabilityContext) -> tuple[dict, str]:
    from agent.core.task_artifacts import read_plan_dict, write_plan_artifact

    task = (ctx.task_id or "").strip()
    mode = (ctx.mode or "code").strip().lower()
    if not task:
        return {}, "missing_task"
    plan = read_plan_dict(task, mode)
    if not plan:
        return {}, "missing_plan"
    return plan, ""


def _run_read(ctx: CapabilityContext, inp: ReadImplementationInput) -> CapabilityResult:
    from agent.core.implementation_plan import (
        ensure_implementation_block,
        format_implementation_for_act,
        render_implementation_plan_markdown,
    )

    plan, err = _load_plan(ctx)
    if err == "missing_task":
        return CapabilityResult.failure("missing_task", "No active task_id for living plan.")
    if err == "missing_plan" or not plan:
        return CapabilityResult.failure("missing_plan", "No plan found for this task.")
    mode = (ctx.mode or "code").strip().lower()
    ensure_implementation_block(plan, mode, user_request=ctx.user_request or "")
    md = render_implementation_plan_markdown(plan, mode=mode)
    compact = format_implementation_for_act(plan)
    return CapabilityResult.success(
        "Living implementation plan loaded.",
        tool_result=md or compact,
        compact=compact,
    )


def _run_update(ctx: CapabilityContext, inp: UpdateChecklistInput) -> CapabilityResult:
    from agent.core.implementation_plan import (
        ensure_implementation_block,
        render_implementation_plan_markdown,
        update_checklist_items,
    )
    from agent.core.task_artifacts import write_plan_artifact

    plan, err = _load_plan(ctx)
    if err == "missing_task":
        return CapabilityResult.failure("missing_task", "No active task_id for living plan.")
    if err == "missing_plan" or not plan:
        return CapabilityResult.failure("missing_plan", "No plan found for this task.")
    mode = (ctx.mode or "code").strip().lower()
    ensure_implementation_block(plan, mode, user_request=ctx.user_request or "")
    if (inp.summary_patch or "").strip():
        impl = plan.setdefault("implementation", {})
        if isinstance(impl, dict):
            impl["summary"] = inp.summary_patch.strip()[:800]
    plan, n = update_checklist_items(
        plan,
        mode=mode,
        item_ids=list(inp.item_ids or []),
        status=inp.status or "done",
        texts_done=list(inp.texts or []),
    )
    write_plan_artifact(ctx.task_id, mode, plan, user_request=ctx.user_request or "")
    md = render_implementation_plan_markdown(plan, mode=mode)
    pending = [
        it
        for it in (plan.get("implementation") or {}).get("checklist") or []
        if isinstance(it, dict) and it.get("status") == "pending"
    ]
    summary = f"Updated {n} checklist item(s). {len(pending)} still pending."
    return CapabilityResult.success(summary, tool_result=md, updated=n, pending=len(pending))


register_capability(
    CapabilitySpec(
        capability_id="cap.plan.read_implementation@v1",
        version="v1",
        title="Read living implementation plan",
        description="Return the current implementation_plan.md / checklist for this task.",
        input_model=ReadImplementationInput,
        handler=_run_read,
        tier="B",
        modes=_LIVING_MODES,
    )
)

register_capability(
    CapabilitySpec(
        capability_id="cap.plan.update_checklist@v1",
        version="v1",
        title="Update living plan checklist",
        description="Mark checklist items done/skipped and refresh implementation_plan.md.",
        input_model=UpdateChecklistInput,
        handler=_run_update,
        tier="B",
        modes=_LIVING_MODES,
    )
)
