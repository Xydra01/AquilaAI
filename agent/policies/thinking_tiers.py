"""Tiered thinking/reflect policy for Aquila surfaces."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ThinkingTier = Literal["micro_structured", "capability_task", "conversational"]

_CAPABILITY_MODES = frozenset({
    "research",
    "writing",
    "character_build",
    "learn_syllabus_build",
    "code",
})

_CONVERSATIONAL_SURFACES = frozenset({"chat", "learn", "character"})


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def harness_force_micro_plan() -> bool:
    return _env_bool("AQUILA_HARNESS_FORCE_MICRO_PLAN", False)


@dataclass(frozen=True)
class ThinkingTierPolicy:
    tier: ThinkingTier
    allow_reflect_pass: bool
    reflect_on_failure_only: bool
    force_act_think_disabled: bool
    act_num_predict: int | None


def resolve_thinking_tier(
    *,
    mode: str = "",
    micro_plan: bool = False,
    surface: str = "chat",
) -> ThinkingTierPolicy:
    """Resolve tier policy from mode, micro-plan flag, and surface."""
    mode_norm = (mode or "").strip().lower()
    surface_key = (surface or "chat").strip().lower()

    if micro_plan and mode_norm == "code":
        from agent.core.loop_settings import (
            act_num_predict_micro_plan,
            act_two_phase_enabled,
            act_two_phase_for_micro_plan,
            reflect_on_failure_enabled,
        )

        allow_reflect = act_two_phase_enabled() and act_two_phase_for_micro_plan()
        rof = reflect_on_failure_enabled(micro_plan=True) if allow_reflect else False
        return ThinkingTierPolicy(
            tier="micro_structured",
            allow_reflect_pass=allow_reflect,
            reflect_on_failure_only=rof,
            force_act_think_disabled=True,
            act_num_predict=act_num_predict_micro_plan(),
        )

    if mode_norm in _CAPABILITY_MODES or surface_key in ("act", "reflect", "plan"):
        from agent.core.loop_settings import (
            act_two_phase_enabled,
            reflect_on_failure_enabled,
        )

        rof = reflect_on_failure_enabled(micro_plan=False)
        return ThinkingTierPolicy(
            tier="capability_task",
            allow_reflect_pass=act_two_phase_enabled(),
            reflect_on_failure_only=rof,
            force_act_think_disabled=True,
            act_num_predict=None,
        )

    return ThinkingTierPolicy(
        tier="conversational",
        allow_reflect_pass=False,
        reflect_on_failure_only=False,
        force_act_think_disabled=False,
        act_num_predict=None,
    )


def should_run_reflect_pass(
    *,
    mode: str = "",
    micro_plan: bool = False,
    parse_retries: int = 0,
    last_act_needs_reflect: bool = False,
    model_name: str | None = None,
) -> bool:
    """Whether the two-phase reflect pass should run before act."""
    tier = resolve_thinking_tier(mode=mode, micro_plan=micro_plan, surface="reflect")
    if not tier.allow_reflect_pass:
        return False
    if parse_retries > 0:
        return True
    if tier.reflect_on_failure_only and not last_act_needs_reflect:
        return False
    from agent.policies.think_policy import resolve_thinking_policy

    policy = resolve_thinking_policy(
        surface="reflect",
        model_name=model_name,
    )
    return policy.think is True


def micro_plan_act_num_predict_enabled() -> bool:
    """True when act turns should use the micro-plan token cap."""
    from agent.core.loop_settings import slot_fill_enabled

    return slot_fill_enabled() or harness_force_micro_plan()
