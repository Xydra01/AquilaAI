"""Writing function module — mode-facing entry points."""
from __future__ import annotations

from typing import Any

from agent.capabilities.adapters import (
    WRITING_DYNAMIC_TEMPLATE_STEPS,
    WRITING_SOURCES_DYNAMIC_TEMPLATE_STEPS,
    WRITING_TEMPLATE_STEPS,
    attach_capability_ids_to_plan,
)
from agent.functions.recipes import RECIPE_REGISTRY, Recipe, get_recipe
from agent.functions.writing_brief import WritingBrief


def resolve_writing_brief_for_task(
    writing_brief: dict[str, Any] | None,
    *,
    has_attachments: bool = False,
) -> WritingBrief:
    if writing_brief:
        brief = WritingBrief.from_plan_dict(writing_brief) or WritingBrief.from_scope_preset("standard")
    else:
        brief = WritingBrief.from_scope_preset("standard")
    brief.has_attachments = bool(has_attachments) or brief.scope == "from_sources"
    if brief.scope == "from_sources":
        brief.has_attachments = True
        brief.advance_when = "scope_met"
    return brief


def resolve_recipe(
    *,
    dynamic_loop: bool = True,
    has_attachments: bool = False,
    writing_brief: dict | None = None,
) -> Recipe:
    brief = WritingBrief.from_plan_dict(writing_brief)
    use_sources = has_attachments or (brief is not None and brief.scope == "from_sources")
    if use_sources:
        return (
            get_recipe("fn.writing.dynamic_work_with_sources")
            or RECIPE_REGISTRY["fn.writing.dynamic_work_with_sources"]
        )
    if dynamic_loop:
        return (
            get_recipe("fn.writing.dynamic_work")
            or RECIPE_REGISTRY["fn.writing.dynamic_work"]
        )
    return get_recipe("fn.writing.full_pipeline") or RECIPE_REGISTRY["fn.writing.full_pipeline"]


def build_capability_plan_from_recipe(
    recipe: Recipe,
    user_request: str,
    *,
    dynamic_loop: bool = True,
    has_attachments: bool = False,
    writing_brief: dict | None = None,
) -> dict:
    brief = WritingBrief.from_plan_dict(writing_brief)
    use_sources = has_attachments or (brief is not None and brief.scope == "from_sources")
    if use_sources:
        template = WRITING_SOURCES_DYNAMIC_TEMPLATE_STEPS
    elif dynamic_loop:
        template = WRITING_DYNAMIC_TEMPLATE_STEPS
    else:
        template = WRITING_TEMPLATE_STEPS
    from agent.core.plan_validator import BUDGET_RUBRIC
    from agent.core.plan_descriptions import capability_step_description

    steps: list[dict] = []
    work_budget = 6
    if brief and brief.advance_when == "scope_met":
        work_budget = 10
    for kind, cap_id in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (4, 6, 8))
        budget = work_budget if kind in ("work", "write") and brief else default
        steps.append({
            "status": "pending",
            "description": capability_step_description(
                "writing", kind, user_request, writing_brief=writing_brief
            ),
            "step_kind": kind,
            "capability_id": cap_id,
            "focus": "write",
            "max_iterations": budget,
        })
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": steps,
        "capability_recipe": recipe.recipe_id,
    }
    if writing_brief:
        plan["writing_brief"] = writing_brief
    return attach_capability_ids_to_plan(plan, mode="writing")


def run_recipe_step(recipe: Recipe, step_index: int, ctx, *, extra_params: dict | None = None):
    from agent.capabilities import run_capability
    from agent.capabilities.base import CapabilityResult

    if step_index < 0 or step_index >= len(recipe.capability_ids):
        return CapabilityResult.failure("bad_index", f"Step index {step_index} out of range.")
    cap_id = recipe.capability_ids[step_index]
    params = dict(extra_params or {})
    if "title" not in params and ctx.user_request:
        params.setdefault("title", ctx.user_request)
    return run_capability(cap_id, ctx, params)
