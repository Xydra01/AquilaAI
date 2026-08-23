"""Research function module — mode-facing entry points."""
from __future__ import annotations

from agent.capabilities.adapters import (
    DYNAMIC_TEMPLATE_CAPABILITY_STEPS,
    OFFLINE_DYNAMIC_TEMPLATE_CAPABILITY_STEPS,
    OFFLINE_TEMPLATE_CAPABILITY_STEPS,
    TEMPLATE_CAPABILITY_STEPS,
    attach_capability_ids_to_plan,
)
from agent.functions.recipes import RECIPE_REGISTRY, Recipe, get_recipe


def resolve_recipe(
    user_request: str,
    *,
    offline: bool = False,
    attachments: list[str] | None = None,
    dynamic_loop: bool | None = None,
) -> Recipe:
    """Select a research recipe from user intent and runtime flags."""
    if dynamic_loop is None:
        try:
            from agent.core.loop_settings import dynamic_loop_enabled

            dynamic_loop = dynamic_loop_enabled()
        except ImportError:
            dynamic_loop = False

    has_attachments = bool(attachments)
    req_lower = (user_request or "").lower()
    journal_only = offline or any(
        phrase in req_lower
        for phrase in ("journal only", "attachments only", "offline", "no web")
    )

    if journal_only or (offline and has_attachments):
        return get_recipe("fn.research.offline_pipeline") or RECIPE_REGISTRY["fn.research.offline_pipeline"]
    if dynamic_loop:
        return get_recipe("fn.research.dynamic_work") or RECIPE_REGISTRY["fn.research.dynamic_work"]
    return get_recipe("fn.research.full_pipeline") or RECIPE_REGISTRY["fn.research.full_pipeline"]


def build_capability_plan_from_recipe(
    recipe: Recipe,
    user_request: str,
    *,
    offline: bool = False,
    dynamic_loop: bool = False,
) -> dict:
    """Build a ledger-compatible plan with capability_id steps."""
    if offline and dynamic_loop:
        template = OFFLINE_DYNAMIC_TEMPLATE_CAPABILITY_STEPS
    elif offline:
        template = OFFLINE_TEMPLATE_CAPABILITY_STEPS
    elif dynamic_loop:
        template = DYNAMIC_TEMPLATE_CAPABILITY_STEPS
    else:
        template = TEMPLATE_CAPABILITY_STEPS

    from agent.core.plan_validator import BUDGET_RUBRIC

    req = (user_request or "Research topic").strip()[:500]
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
    return attach_capability_ids_to_plan(plan, offline=offline)


def run_recipe_step(
    recipe: Recipe,
    step_index: int,
    ctx,
    *,
    extra_params: dict | None = None,
) -> "CapabilityResult":
    """Run the capability for a recipe step index (code-first orchestration)."""
    from agent.capabilities import run_capability
    from agent.capabilities.base import CapabilityResult

    if step_index < 0 or step_index >= len(recipe.capability_ids):
        return CapabilityResult.failure("bad_index", f"Step index {step_index} out of range.")
    cap_id = recipe.capability_ids[step_index]
    params = dict(extra_params or {})
    if "topic" not in params and ctx.user_request:
        params.setdefault("topic", ctx.user_request)
    return run_capability(cap_id, ctx, params)


def recommended_capability_for_step(
    step: dict,
    user_request: str,
    *,
    offline: bool = False,
    has_attachments: bool = False,
    caps_succeeded: set[str] | None = None,
) -> tuple[str, dict]:
    """Default capability + args for a plan step (recipe/ledger driven)."""
    from agent.capabilities.adapters import default_capability_for_step

    done = caps_succeeded or set()
    kind = (step.get("step_kind") or "work").strip().lower()
    params_base: dict = dict(step.get("params") or {})
    params_base.setdefault("topic", (user_request or "Research topic").strip()[:500])

    if offline and kind == "work":
        if "cap.research.ingest_offline@v1" not in done:
            return "cap.research.ingest_offline@v1", dict(params_base)
        if "cap.research.synthesize_notes@v1" not in done:
            return "cap.research.synthesize_notes@v1", dict(params_base)

    cap_id = step.get("capability_id") or default_capability_for_step(
        kind,
        offline=offline,
        has_attachments=has_attachments,
    )
    if not cap_id:
        cap_id = "cap.research.gather_web_sources@v1"
    return str(cap_id), dict(params_base)
