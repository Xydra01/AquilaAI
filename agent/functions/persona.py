"""Persona function module — mode-facing entry points."""
from __future__ import annotations

from agent.capabilities.adapters import (
    PERSONA_LORE_TEMPLATE_STEPS,
    PERSONA_TEMPLATE_STEPS,
    attach_capability_ids_to_plan,
)
from agent.functions.recipes import RECIPE_REGISTRY, Recipe, get_recipe


def resolve_recipe(*, persona_research_lore: bool = False) -> Recipe:
    if persona_research_lore:
        return (
            get_recipe("fn.persona.build_with_lore")
            or RECIPE_REGISTRY["fn.persona.build_with_lore"]
        )
    return get_recipe("fn.persona.build") or RECIPE_REGISTRY["fn.persona.build"]


def build_capability_plan_from_recipe(
    recipe: Recipe,
    user_request: str,
    *,
    persona_research_lore: bool = False,
) -> dict:
    template = (
        PERSONA_LORE_TEMPLATE_STEPS if persona_research_lore else PERSONA_TEMPLATE_STEPS
    )
    from agent.core.plan_validator import BUDGET_RUBRIC

    req = (user_request or "Persona").strip()[:500]
    steps: list[dict] = []
    for kind, cap_id in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
        steps.append({
            "status": "pending",
            "description": f"{kind}: {req}",
            "step_kind": kind,
            "capability_id": cap_id,
            "params": {"topic": req} if "gather" in cap_id or "ingest" in cap_id else {},
            "max_iterations": default,
        })
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": steps,
        "capability_recipe": recipe.recipe_id,
    }
    return attach_capability_ids_to_plan(
        plan,
        mode="character_build",
        persona_research_lore=persona_research_lore,
    )


def run_recipe_step(recipe: Recipe, step_index: int, ctx, *, extra_params: dict | None = None):
    from agent.capabilities import run_capability
    from agent.capabilities.base import CapabilityResult

    if step_index < 0 or step_index >= len(recipe.capability_ids):
        return CapabilityResult.failure("bad_index", f"Step index {step_index} out of range.")
    cap_id = recipe.capability_ids[step_index]
    params = dict(extra_params or {})
    if "topic" not in params and ctx.user_request:
        params.setdefault("topic", ctx.user_request)
    return run_capability(cap_id, ctx, params)
