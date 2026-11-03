"""Feature flags and limits for the dynamic (milestone-driven) act loop."""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def run_state_enabled() -> bool:
    """When True: per-task RunState drives prompt context (digest, ground truth, checkpoints)."""
    return _env_bool("AQUILA_RUN_STATE_ENABLED", True)


def run_digest_compress_enabled() -> bool:
    return _env_bool("AQUILA_RUN_DIGEST_COMPRESS", True)


def capability_repeat_guard_enabled() -> bool:
    return _env_bool("AQUILA_CAPABILITY_REPEAT_GUARD", True)


def dynamic_loop_enabled() -> bool:
    """When True: mode-wide tool palette, milestone advance, task episode budget."""
    return _env_bool("AQUILA_DYNAMIC_LOOP", False)


def auto_advance_milestones_enabled() -> bool:
    return _env_bool("AQUILA_AUTO_ADVANCE_MILESTONES", False)


def task_episode_max() -> int:
    raw = os.getenv("AQUILA_TASK_EPISODE_MAX", "32").strip()
    try:
        return max(8, int(raw))
    except ValueError:
        return 32


def task_web_search_cap() -> int:
    """Max web_search tool runs per task (dynamic loop anti-spiral)."""
    raw = os.getenv("AQUILA_TASK_WEB_SEARCH_CAP", "12").strip()
    try:
        return max(2, int(raw))
    except ValueError:
        return 12


def dynamic_schema_max_tools() -> int:
    """Max tools in act JSON schema when AQUILA_DYNAMIC_LOOP=1 (smaller = fewer parse errors)."""
    raw = os.getenv("AQUILA_DYNAMIC_SCHEMA_MAX_TOOLS", "128").strip()
    try:
        return max(12, min(256, int(raw)))
    except ValueError:
        return 128


def act_two_phase_enabled() -> bool:
    """When True: native think pass, then structured tool JSON act pass per loop tick."""
    return _env_bool("AQUILA_ACT_TWO_PHASE", True)


def act_two_phase_for_micro_plan() -> bool:
    """When False (default): micro-plan code tasks skip the reflect pass."""
    return _env_bool("AQUILA_ACT_TWO_PHASE_MICRO", False)


def reflect_on_failure_enabled(*, micro_plan: bool = False) -> bool:
    """When True: skip reflect unless last act failed, was blocked, or parse retried."""
    if micro_plan:
        return False
    raw = os.getenv("AQUILA_REFLECT_ON_FAILURE", "").strip()
    if raw:
        return raw.lower() not in ("0", "false", "no", "off")
    return True


def think_min_prompt_tokens() -> int:
    """Min estimated prompt tokens before native think on chat/learn surfaces."""
    from agent.policies.think_policy import think_min_prompt_tokens as _min

    return _min()


def run_digest_compress_for_micro_plan() -> bool:
    """When False (default): micro-plan tasks skip run-state digest compression chat."""
    return _env_bool("AQUILA_RUN_DIGEST_COMPRESS_MICRO", False)


def slot_fill_enabled() -> bool:
    """When True: act schema omits capability id; OS binds cap per step."""
    return _env_bool("AQUILA_SLOT_FILL", False)


def scaffold_dispatch_enabled() -> bool:
    """When True: known greenfield goals may pre-write scaffold files without LLM."""
    return _env_bool("AQUILA_SCAFFOLD_DISPATCH", False)


def act_structured_no_plain_enabled() -> bool:
    """When True: act surfaces skip plain-text structured-output fallback."""
    return _env_bool("AQUILA_ACT_STRUCTURED_NO_PLAIN", True)


def plan_structured_no_plain_enabled() -> bool:
    """When True: plan surfaces skip plain-text structured-output fallback."""
    return _env_bool("AQUILA_PLAN_STRUCTURED_NO_PLAIN", True)


def plan_num_predict() -> int:
    """Token cap for plan JSON generation (prevents 5k+ token runaway plans)."""
    raw = os.getenv("AQUILA_PLAN_NUM_PREDICT", "2048").strip()
    try:
        return max(512, min(4096, int(raw)))
    except ValueError:
        return 2048


def act_num_predict_micro_plan() -> int:
    """Token cap for micro-plan slot-fill act turns (keeps file bodies small)."""
    raw = os.getenv("AQUILA_ACT_NUM_PREDICT_MICRO", "1024").strip()
    try:
        return max(256, min(2048, int(raw)))
    except ValueError:
        return 1024


def plan_review_enabled() -> bool:
    """When True: pause after planning for user approval before act loop."""
    return _env_bool("AQUILA_PLAN_REVIEW", True)


def plan_auto_approve_micro_enabled() -> bool:
    """When True: micro-plans skip the plan review gate."""
    return _env_bool("AQUILA_PLAN_AUTO_APPROVE_MICRO", False)


def walkthrough_enabled() -> bool:
    """When True: generate walkthrough.md on finish_task."""
    return _env_bool("AQUILA_WALKTHROUGH", True)


def llm_error_limit() -> int:
    """Consecutive LLM (Ollama) failures before the loop aborts."""
    raw = os.getenv("AQUILA_LLM_ERROR_LIMIT", "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def research_recipe_strict_enabled() -> bool:
    """When True: first act turn auto-runs step capability_id from plan."""
    return _env_bool("AQUILA_RESEARCH_RECIPE_STRICT", False)
