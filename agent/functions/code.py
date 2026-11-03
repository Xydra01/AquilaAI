"""Code function module — mode-facing entry points."""
from __future__ import annotations

from agent.capabilities.adapters import (
    CODE_DOC_TEMPLATE_STEPS,
    CODE_DYNAMIC_TEMPLATE_STEPS,
    CODE_IMPLEMENT_TEMPLATE_STEPS,
    CODE_TDD_TEMPLATE_STEPS,
    attach_capability_ids_to_plan,
)
from agent.functions.recipes import RECIPE_REGISTRY, Recipe, get_recipe


def resolve_recipe(
    *,
    dynamic_loop: bool = True,
    documentation: bool = False,
    tdd: bool = False,
) -> Recipe:
    if documentation:
        return get_recipe("fn.dev.documentation") or RECIPE_REGISTRY["fn.dev.documentation"]
    if tdd:
        return get_recipe("fn.dev.tdd") or RECIPE_REGISTRY["fn.dev.tdd"]
    if dynamic_loop:
        return get_recipe("fn.dev.dynamic_work") or RECIPE_REGISTRY["fn.dev.dynamic_work"]
    return get_recipe("fn.dev.implement") or RECIPE_REGISTRY["fn.dev.implement"]


def build_capability_plan_from_recipe(
    recipe: Recipe,
    user_request: str,
    *,
    dynamic_loop: bool = True,
    documentation: bool = False,
    tdd: bool = False,
) -> dict:
    if documentation:
        template = CODE_DOC_TEMPLATE_STEPS
    elif tdd:
        template = CODE_TDD_TEMPLATE_STEPS
    elif dynamic_loop:
        template = CODE_DYNAMIC_TEMPLATE_STEPS
    else:
        template = CODE_IMPLEMENT_TEMPLATE_STEPS
    from agent.core.plan_validator import BUDGET_RUBRIC
    from agent.core.plan_descriptions import capability_step_description

    steps: list[dict] = []
    for kind, cap_id in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (4, 6, 8))
        steps.append({
            "status": "pending",
            "description": capability_step_description("code", kind, user_request),
            "step_kind": kind,
            "capability_id": cap_id,
            "focus": "code",
            "max_iterations": default,
        })
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": steps,
        "capability_recipe": recipe.recipe_id,
    }
    return attach_capability_ids_to_plan(plan, mode="code")
