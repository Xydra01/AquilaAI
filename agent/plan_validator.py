"""
Budget-aware plan validation and tuning for Aquila OS 3.3.
"""
from __future__ import annotations

import json
import re
from typing import Any

STEP_KINDS = (
    "search",
    "read",
    "code",
    "verify",
    "synthesize",
    "write",
    "finalize",
    "tdd_red",
    "tdd_green",
    "tdd_refactor",
)

# min, default, max iterations per step_kind
BUDGET_RUBRIC: dict[str, tuple[int, int, int]] = {
    "search": (3, 4, 6),
    "read": (3, 5, 7),
    "code": (4, 6, 10),
    "verify": (3, 4, 6),
    "synthesize": (5, 6, 9),
    "write": (4, 5, 8),
    "finalize": (4, 6, 8),
    "tdd_red": (4, 5, 6),
    "tdd_green": (6, 8, 10),
    "tdd_refactor": (4, 5, 6),
}

MAX_PLAN_STEPS = 8
MAX_TOTAL_BUDGET = 60

_KIND_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("finalize", ("final report", "finalize", "finish task", "deliverable", "wrap up")),
    ("search", ("search", "find", "query", "look up", "web", "google")),
    ("read", ("read", "fetch", "scrape", "extract", "pull", "download")),
    ("tdd_red", ("failing test", "write test", "tdd red", "red phase", "test first")),
    ("tdd_green", ("implement", "make test pass", "tdd green", "green phase", "minimal code")),
    ("tdd_refactor", ("refactor", "clean up", "tdd refactor", "improve code")),
    ("verify", ("verify", "validate", "check", "confirm", "grep", "lint", "full pytest")),
    ("synthesize", ("synthesize", "compile", "summarize", "compare", "analyze")),
    ("write", ("write", "draft", "document", "section", "essay", "outline")),
    ("code", ("create", "build", "script", "file", "run")),
]

STEP_KIND_HINTS: dict[str, str] = {
    "search": "Prefer web_search, then read_webpage for top URLs. Batch reads.",
    "read": "Use read_webpage or read_file; avoid re-reading the same URL/file.",
    "code": "Use init_code_project, replace_lines, apply_unified_patch; run_pytest to verify.",
    "verify": "Prefer search_in_file or search_files over read_file per file.",
    "synthesize": "Use save_research_note for snippets; keep notes under 8KB.",
    "write": "Use write_section with grouped subsections; read_outline if needed.",
    "finalize": "Put the full report in top-level final_report; finish_task on last step.",
    "tdd_red": "Write/update pytest test; run_pytest must show FAILED before mark_objective_complete.",
    "tdd_green": "Minimal implementation; use replace_lines/replace_symbol; run_pytest until PASSED.",
    "tdd_refactor": "Refactor only; run_pytest after edits; tests must stay green.",
}

MODE_MIN_STEPS: dict[str, int] = {
    "research": 4,
    "writing": 3,
    "task": 2,
    "autonomous": 2,
    "code": 4,
}

TDD_KEYWORDS = ("implement", "build", "feature", "fix bug", "add ", "create ", "tdd", "pytest")


def infer_step_kind(description: str, mode: str, step_index: int, total_steps: int) -> str:
    text = (description or "").lower()
    for kind, keywords in _KIND_KEYWORDS:
        if any(kw in text for kw in keywords):
            return kind
    if step_index == total_steps - 1:
        return "finalize"
    if mode == "research":
        return "search" if step_index == 0 else "read"
    if mode == "writing":
        return "write"
    if mode == "code":
        return "read" if step_index == 0 else "code"
    return "code"


def get_step_kind_hint(step_kind: str) -> str:
    return STEP_KIND_HINTS.get(step_kind, "Complete the objective efficiently; avoid duplicate tool calls.")


def _clamp_budget(step_kind: str, max_iterations: int | None) -> int:
    lo, default, hi = BUDGET_RUBRIC.get(step_kind, (3, 4, 6))
    value = default if max_iterations is None else int(max_iterations)
    return max(lo, min(hi, value))


def validate_and_tune_plan(
    plan: dict[str, Any],
    mode: str,
    user_request: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """
    Ensure step_kind and realistic max_iterations; cap steps and total budget.
    Returns (tuned_plan, list of human-readable tuning notes).
    """
    notes: list[str] = []
    mode_key = mode if mode in MODE_MIN_STEPS else "task"
    if mode == "autonomous":
        mode_key = "task"

    steps = plan.get("steps")
    if not isinstance(steps, list):
        steps = []
        plan["steps"] = steps

    if len(steps) > MAX_PLAN_STEPS:
        notes.append(f"Trimmed plan from {len(steps)} to {MAX_PLAN_STEPS} steps.")
        steps = steps[:MAX_PLAN_STEPS]
        plan["steps"] = steps

    total_steps = len(steps)
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        desc = step.get("description", "")
        kind = step.get("step_kind")
        if kind not in STEP_KINDS:
            kind = infer_step_kind(desc, mode_key if mode != "code" else "code", i, total_steps)
            step["step_kind"] = kind
            notes.append(f"Step {i + 1}: inferred step_kind={kind}.")

        old_budget = step.get("max_iterations")
        new_budget = _clamp_budget(kind, old_budget)
        if old_budget != new_budget:
            notes.append(
                f"Step {i + 1} ({kind}): max_iterations {old_budget} -> {new_budget}."
            )
        step["max_iterations"] = new_budget
        if step.get("status") is None:
            step["status"] = "pending"

    total_budget = sum(s.get("max_iterations", 4) for s in steps if isinstance(s, dict))
    while total_budget > MAX_TOTAL_BUDGET and steps:
        reduced = False
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            kind = step.get("step_kind", "code")
            lo, _, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
            if step["max_iterations"] > lo:
                step["max_iterations"] -= 1
                total_budget -= 1
                reduced = True
                if total_budget <= MAX_TOTAL_BUDGET:
                    break
        if reduced:
            notes.append(f"Reduced total budget to {total_budget} (cap {MAX_TOTAL_BUDGET}).")
        else:
            break

    min_steps = MODE_MIN_STEPS.get(mode_key, 2)
    if len(steps) < min_steps and mode_key == "research":
        notes.append(
            f"Research plan has only {len(steps)} steps; consider at least {min_steps} "
            "(search, read, notes, synthesize)."
        )

    if mode == "code" and user_request:
        req_lower = user_request.lower()
        if any(kw in req_lower for kw in TDD_KEYWORDS) and len(steps) < 4:
            notes.append(
                "Code TDD workflow recommended: explore → tdd_red → tdd_green → verify → finalize."
            )

    plan.setdefault("status", "in_progress")
    plan.setdefault("current_step_index", 0)
    return plan, notes


def tune_plan_json(plan_json: str, mode: str, user_request: str = "") -> tuple[str, list[str]]:
    """Parse JSON plan string, tune, return serialized JSON and notes."""
    plan = json.loads(plan_json)
    tuned, notes = validate_and_tune_plan(plan, mode, user_request)
    return json.dumps(tuned, indent=2), notes
