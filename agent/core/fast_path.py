"""Heuristic micro-plan fast path — skip full LLM planning for simple objectives."""
from __future__ import annotations

import json
import os
import re
from typing import Any

_COMPLEX_KEYWORDS = re.compile(
    r"\b("
    r"refactor|multi[- ]file|entire|comprehensive|architecture|migrate|"
    r"multiple|workflow|pipeline|integration test|full test suite|"
    r"deep[- ]dive|compare and contrast|literature review|"
    r"autonomous|end[- ]to[- ]end|from scratch|large codebase"
    r")\b",
    re.I,
)

_MULTI_STEP = re.compile(
    r"\b(then|after that|step \d|first.*second|also.*and)\b",
    re.I,
)

_MODES_WITH_FAST_PATH = frozenset({"writing", "research"})  # code: DEAD — uses code_agent, no micro-plan


def fast_path_enabled() -> bool:
    raw = os.getenv("AQUILA_FAST_PATH", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def always_full_plan_enabled() -> bool:
    """When True: never use micro-plans, even for short/simple tasks."""
    raw = os.getenv("AQUILA_ALWAYS_FULL_PLAN", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def micro_plan_max_words() -> int:
    raw = os.getenv("AQUILA_MICRO_PLAN_MAX_WORDS", "80").strip()
    try:
        return max(10, int(raw))
    except ValueError:
        return 80


def explore_brief_enabled(mode: str, user_request: str, *, micro_plan: bool = False) -> bool:
    if micro_plan:
        return False
    if (mode or "").strip().lower() == "code":
        return False  # DEAD: code uses code_agent.py
    raw = os.getenv("AQUILA_EXPLORE_BRIEF", "0").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if mode not in ("research",):
        return False
    try:
        from agent.policies import get_context_profile

        if get_context_profile().tier not in ("extended", "max"):
            return False
    except Exception:
        return False
    if _COMPLEX_KEYWORDS.search(user_request or ""):
        return True
    return False


def harness_force_micro_plan() -> bool:
    raw = os.getenv("AQUILA_HARNESS_FORCE_MICRO_PLAN", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def should_micro_plan(
    mode: str,
    user_request: str,
    *,
    text_chunks: list | None = None,
    image_payloads: list | None = None,
) -> bool:
    mode_norm = (mode or "task").strip().lower()
    # DEAD: code uses code_agent.py — never micro-plan / slot-fill for code.
    if mode_norm == "code":
        return False
    if harness_force_micro_plan():
        return mode_norm in _MODES_WITH_FAST_PATH
    text = (user_request or "").strip()
    # Habit-tracker greenfield prompts always use the OS TDD micro-plan (slot-fill).
    # (Removed for code mode — see early return above.)
    if always_full_plan_enabled():
        return False
    try:
        from .loop_settings import (
            dynamic_loop_enabled,
            plan_auto_approve_micro_enabled,
            plan_review_enabled,
        )

        # Dynamic loop expects milestone-first LLM planning, not heuristic steps.
        if dynamic_loop_enabled():
            return False
        # When plan review is on and micro auto-approve is off, use the full planner.
        if plan_review_enabled() and not plan_auto_approve_micro_enabled():
            return False
    except ImportError:
        pass
    if not fast_path_enabled():
        return False
    if mode_norm not in _MODES_WITH_FAST_PATH:
        return False
    if text_chunks or image_payloads:
        return False
    text = (user_request or "").strip()
    if not text:
        return False
    words = text.split()
    if len(words) > micro_plan_max_words():
        return False
    if _COMPLEX_KEYWORDS.search(text):
        return False
    if _MULTI_STEP.search(text):
        return False
    if text.count("\n") > 4:
        return False
    return True


def _dynamic_work_finalize(mode_norm: str, objective: str) -> list[dict[str, Any]]:
    from .plan_validator import BUDGET_RUBRIC

    _, work_default, _ = BUDGET_RUBRIC.get("work", (8, 14, 24))
    _, fin_default, _ = BUDGET_RUBRIC.get("finalize", (4, 6, 8))
    finalize_step: dict[str, Any] = {
        "status": "pending",
        "description": "Finalize deliverable report",
        "step_kind": "finalize",
        "focus": "deliver",
        "max_iterations": fin_default,
    }
    if mode_norm == "research":
        finalize_step["capability_id"] = "cap.research.finalize_deliverable@v1"
    elif mode_norm == "writing":
        finalize_step["capability_id"] = "cap.writing.finalize_deliverable@v1"
    elif mode_norm == "code":
        finalize_step["description"] = "Sync via cap.dev.sync_project@v1"
        finalize_step["capability_id"] = "cap.dev.sync_project@v1"
    work_step: dict[str, Any] = {
        "status": "pending",
        "description": objective[:240],
        "step_kind": "work" if mode_norm != "writing" else "write",
        "focus": mode_norm if mode_norm != "writing" else "write",
        "max_iterations": work_default,
    }
    if mode_norm == "writing":
        work_step["capability_id"] = "cap.writing.draft_sections@v1"
    elif mode_norm == "code":
        work_step["description"] = f"Create files via cap.dev.create_file@v1: {objective[:160]}"
        work_step["capability_id"] = "cap.dev.create_file@v1"
    return [work_step, finalize_step]


def _habit_tracker_micro_steps(objective: str) -> list[dict[str, Any]]:
    """TDD micro-plan for tiny habit-tracker greenfield prompts."""
    use_batch = os.getenv("AQUILA_CODE_BATCH_WRITE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if use_batch:
        work_cap = "cap.dev.write_files@v1"
        work_desc = "Write tests, habit.py, and README in one batch"
        work_kind = "work"
    else:
        work_cap = "cap.dev.create_file@v1"
        work_desc = "Write failing tests (tests/test_habit.py)"
        work_kind = "tdd_red"
    steps: list[dict[str, Any]] = [
        {
            "status": "pending",
            "description": work_desc,
            "step_kind": work_kind,
            "capability_id": work_cap,
            "slot_fill": True,
            "slot_fill_path": "tests/test_habit.py",
            "max_iterations": 4,
        },
    ]
    if not use_batch:
        steps.append(
            {
                "status": "pending",
                "description": "Implement habit.py CLI (add / done / list)",
                "step_kind": "tdd_green",
                "capability_id": "cap.dev.create_file@v1",
                "slot_fill": True,
                "slot_fill_path": "habit.py",
                "max_iterations": 4,
            }
        )
        steps.append(
            {
                "status": "pending",
                "description": "Run pytest until green",
                "step_kind": "verify",
                "capability_id": "cap.dev.run_tests@v1",
                "slot_fill": True,
                "max_iterations": 3,
            }
        )
        steps.append(
            {
                "status": "pending",
                "description": "Write README.md",
                "step_kind": "work",
                "capability_id": "cap.dev.create_file@v1",
                "slot_fill": True,
                "slot_fill_path": "README.md",
                "max_iterations": 3,
            }
        )
    else:
        steps.append(
            {
                "status": "pending",
                "description": "Run pytest until green",
                "step_kind": "verify",
                "capability_id": "cap.dev.run_tests@v1",
                "slot_fill": True,
                "max_iterations": 3,
            }
        )
    steps.append(
        {
            "status": "pending",
            "description": "Sync via cap.dev.sync_project@v1",
            "step_kind": "finalize",
            "capability_id": "cap.dev.sync_project@v1",
            "slot_fill": True,
            "max_iterations": 4,
        }
    )
    _ = objective
    return steps


def _step_for_mode(mode: str, objective: str) -> list[dict[str, Any]]:
    mode_norm = (mode or "task").strip().lower()
    if mode_norm == "code":
        # DEAD: code uses code_agent — return empty (should_micro_plan already False).
        return []
    try:
        from .loop_settings import dynamic_loop_enabled

        if dynamic_loop_enabled() and mode_norm in ("research", "writing"):
            return _dynamic_work_finalize(mode_norm, objective)
    except ImportError:
        pass
    if mode_norm == "research":
        return [
            {
                "status": "pending",
                "description": f"Search and summarize: {objective[:200]}",
                "step_kind": "search",
                "capability_id": "cap.research.gather_web_sources@v1",
                "max_iterations": 4,
            },
            {
                "status": "pending",
                "description": f"Compile findings: {objective[:200]}",
                "step_kind": "synthesize",
                "capability_id": "cap.research.synthesize_notes@v1",
                "max_iterations": 3,
            },
        ]
    if mode_norm == "writing":
        return [
            {
                "status": "pending",
                "description": f"Draft: {objective[:200]}",
                "step_kind": "write",
                "capability_id": "cap.writing.draft_sections@v1",
                "max_iterations": 4,
            },
            {
                "status": "pending",
                "description": "Finalize deliverable report",
                "step_kind": "finalize",
                "capability_id": "cap.writing.finalize_deliverable@v1",
                "max_iterations": 3,
            },
        ]
    return [
        {
            "status": "pending",
            "description": objective[:240],
            "step_kind": "micro",
            "max_iterations": 4,
        }
    ]


def build_micro_plan(mode: str, user_request: str, task_name: str) -> str:
    objective = (user_request or task_name or "Complete task").strip()
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "micro_plan": True,
        "task_name": task_name,
        "steps": _step_for_mode(mode, objective),
    }
    return json.dumps(plan, indent=2)
