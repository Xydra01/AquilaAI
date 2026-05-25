"""
Budget-aware plan validation and tuning for Aquila OS 3.3.
"""
from __future__ import annotations

import json
import re
from typing import Any

STEP_KINDS = (
    "explore",
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

# min, default, max episodes per step_kind (stored as max_iterations in ledger JSON)
BUDGET_RUBRIC: dict[str, tuple[int, int, int]] = {
    "explore": (5, 8, 12),
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
    ("explore", ("explore", "recon", "outline", "survey", "map codebase", "discover")),
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
    "explore": "Read-only recon: get_directory_tree (once), read_code_outline, read_file_region; index/search optional. Max 2 list_directory per step. No mark_objective_complete until evidence exists.",
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
    "character_build": 3,
    "learn_syllabus_build": 3,
}

TDD_KEYWORDS = ("implement", "build", "feature", "fix bug", "add ", "create ", "tdd", "pytest")

MAX_STEP_DESCRIPTION_CHARS = 600
_RESEARCH_STEP_KINDS = ("search", "read", "synthesize", "finalize")
_CHARACTER_BUILD_STEP_KINDS = ("read", "synthesize", "finalize")
_CHARACTER_BUILD_LORE_STEP_KINDS = ("search", "read", "synthesize", "finalize")
_LEARN_SYLLABUS_STEP_KINDS = ("read", "synthesize", "finalize")
_LEARN_SYLLABUS_WEB_STEP_KINDS = ("search", "read", "synthesize", "finalize")

_FALLBACK_DESCRIPTIONS: dict[str, str] = {
    "explore": "Reconnaissance: survey sources and codebase before deeper work.",
    "search": "Search authoritative web sources for the research topic.",
    "read": "Read and extract key facts from top URLs (NASA, .gov, .edu).",
    "synthesize": "Save research notes and compare findings.",
    "finalize": "Write final_report with bibliography and call finish_task.",
    "write": "Draft the assigned writing section.",
    "code": "Implement or edit code for this step.",
    "verify": "Verify outputs (tests, grep, lint).",
}


def _collapse_comma_repetition(text: str) -> str:
    """Collapse runs like 'radius, radius, radius, ...' into a single token."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 8:
        return text
    collapsed: list[str] = []
    for part in parts:
        if collapsed and part.lower() == collapsed[-1].lower():
            continue
        collapsed.append(part)
    if len(collapsed) < len(parts) * 0.5:
        return ", ".join(collapsed[:12])
    return text


def is_degenerate_description(description: str) -> bool:
    """Detect LLM repetition loops or runaway plan step text."""
    text = (description or "").strip()
    if len(text) > MAX_STEP_DESCRIPTION_CHARS * 2:
        return True
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 12:
        return False
    from collections import Counter

    _top_word, top_count = Counter(words).most_common(1)[0]
    if top_count / len(words) > 0.35:
        return True
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    if len(parts) >= 15:
        unique_ratio = len(set(parts)) / len(parts)
        if unique_ratio < 0.25:
            return True
    return False


def sanitize_step_description(
    description: str,
    *,
    step_kind: str = "",
    step_index: int = 0,
    total_steps: int = 1,
) -> tuple[str, bool]:
    """
    Trim and repair step descriptions. Returns (cleaned_text, was_modified).
    """
    raw = (description or "").strip()
    if not raw:
        kind = step_kind or "code"
        return _FALLBACK_DESCRIPTIONS.get(kind, "Complete this step."), True

    cleaned = _collapse_comma_repetition(raw)
    modified = cleaned != raw
    heavy_repetition = modified and len(raw) > 200 and len(cleaned) < len(raw) * 0.15

    if heavy_repetition or is_degenerate_description(cleaned):
        kind = step_kind or infer_step_kind(cleaned[:200], "research", step_index, total_steps)
        cleaned = _FALLBACK_DESCRIPTIONS.get(kind, cleaned[:MAX_STEP_DESCRIPTION_CHARS])
        modified = True

    if len(cleaned) > MAX_STEP_DESCRIPTION_CHARS:
        cleaned = cleaned[: MAX_STEP_DESCRIPTION_CHARS - 3].rstrip() + "..."
        modified = True

    return cleaned, modified


def infer_step_kind(description: str, mode: str, step_index: int, total_steps: int) -> str:
    if mode == "research" and total_steps >= 4 and step_index < len(_RESEARCH_STEP_KINDS):
        return _RESEARCH_STEP_KINDS[step_index]
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


def expand_research_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    explore_brief_ran: bool = False,
) -> tuple[dict[str, Any], str]:
    """
    Replace an under-sized research plan with a standard multi-step template.
    Omits a dedicated explore step when the explore brief already ran.
    """
    steps = plan.get("steps") or []
    original_desc = ""
    if steps and isinstance(steps[0], dict):
        original_desc = str(steps[0].get("description", "")).strip()[:400]

    req = (user_request or "the research topic").strip()[:500]
    brief_note = (
        " (Explore brief already completed — skip redundant recon; go straight to search.)"
        if explore_brief_ran
        else ""
    )

    template: list[tuple[str, str]] = [
        (
            "search",
            f"Web search for authoritative sources on: {req}.{brief_note}",
        ),
        (
            "read",
            f"Read and extract key facts from top URLs (NASA, .gov, .edu) for: {req}.",
        ),
        (
            "synthesize",
            f"Save research notes (save_research_note) comparing findings for: {req}.",
        ),
        (
            "finalize",
            f"Write final_report with bibliography and call finish_task for: {req}.",
        ),
    ]

    new_steps: list[dict[str, Any]] = []
    for kind, desc in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
        new_steps.append({
            "status": "pending",
            "description": desc,
            "step_kind": kind,
            "max_iterations": default,
        })

    if original_desc and original_desc not in new_steps[0]["description"]:
        new_steps[0]["description"] += f" Prior planner note: {original_desc}"

    old_count = len(steps)
    plan["steps"] = new_steps
    note = f"Expanded research plan from {old_count} to {len(new_steps)} steps."
    if explore_brief_ran:
        note += " Explore brief already ran; template starts at search."
    return plan, note


def expand_character_build_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    persona_research_lore: bool = False,
) -> tuple[dict[str, Any], str]:
    """Replace an under-sized or legacy persona-build plan with the standard template."""
    steps = plan.get("steps") or []
    original_desc = ""
    if steps and isinstance(steps[0], dict):
        original_desc = str(steps[0].get("description", "")).strip()[:400]

    req = (user_request or "the persona").strip()[:500]
    if persona_research_lore:
        template: list[tuple[str, str]] = [
            (
                "search",
                f"Research lore on the web: web_search and read_webpage for {req}; "
                "save_research_note with findings (no write_persona_file).",
            ),
            (
                "read",
                f"Merge user description and attachments via save_research_note if needed "
                f"(no write_persona_file). Topic: {req}.",
            ),
            (
                "synthesize",
                f"read_all_research_notes then write_persona_file once for initialization.md: {req}.",
            ),
            (
                "finalize",
                f"finalize_persona (greeting + tagline) then finish_task for: {req}.",
            ),
        ]
    else:
        template = [
            (
                "read",
                f"Ingest user description and attachments via save_research_note only "
                f"(no write_persona_file). Topic: {req}.",
            ),
            (
                "synthesize",
                f"read_all_research_notes then write_persona_file once for initialization.md: {req}.",
            ),
            (
                "finalize",
                f"finalize_persona (greeting + tagline) then finish_task for: {req}.",
            ),
        ]

    new_steps: list[dict[str, Any]] = []
    for kind, desc in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
        new_steps.append({
            "status": "pending",
            "description": desc,
            "step_kind": kind,
            "max_iterations": default,
        })

    if original_desc and original_desc not in new_steps[0]["description"]:
        new_steps[0]["description"] += f" Prior planner note: {original_desc}"

    old_count = len(steps)
    plan["steps"] = new_steps
    plan["current_step_index"] = 0
    plan["status"] = "in_progress"
    note = f"Expanded character_build plan from {old_count} to {len(new_steps)} steps."
    return plan, note


def expand_learn_syllabus_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    learn_syllabus_web: bool = False,
) -> tuple[dict[str, Any], str]:
    """Replace under-sized learn syllabus build plan with standard template."""
    steps = plan.get("steps") or []
    req = (user_request or "the course").strip()[:500]
    if learn_syllabus_web:
        template: list[tuple[str, str]] = [
            (
                "search",
                f"Web research for course topic: web_search, read_webpage, save_research_note. {req}",
            ),
            (
                "read",
                f"Ingest uploaded sources via save_research_note. {req}",
            ),
            (
                "synthesize",
                "read_all_research_notes then write_syllabus_file (JSON with nodes, mastery tiers). "
                "Add generate_assessment for key nodes.",
            ),
            (
                "finalize",
                "finalize_course then finish_task.",
            ),
        ]
    else:
        template = [
            (
                "read",
                f"Ingest topic and attachments via save_research_note. {req}",
            ),
            (
                "synthesize",
                "read_all_research_notes then write_syllabus_file once (JSON syllabus).",
            ),
            (
                "finalize",
                "finalize_course then finish_task.",
            ),
        ]
    new_steps: list[dict[str, Any]] = []
    for kind, desc in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
        new_steps.append({
            "status": "pending",
            "description": desc,
            "step_kind": kind,
            "max_iterations": default,
        })
    old_count = len(steps)
    plan["steps"] = new_steps
    plan["current_step_index"] = 0
    plan["status"] = "in_progress"
    return plan, f"Expanded learn_syllabus_build plan from {old_count} to {len(new_steps)} steps."


def validate_and_tune_plan(
    plan: dict[str, Any],
    mode: str,
    user_request: str = "",
    *,
    explore_brief_ran: bool = False,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
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
        if mode_key == "research" and total_steps >= 4 and i < len(_RESEARCH_STEP_KINDS):
            kind = _RESEARCH_STEP_KINDS[i]
            step["step_kind"] = kind
        elif mode_key == "character_build":
            lore_kinds = _CHARACTER_BUILD_LORE_STEP_KINDS
            std_kinds = _CHARACTER_BUILD_STEP_KINDS
            kinds = lore_kinds if persona_research_lore else std_kinds
            if total_steps >= len(kinds) and i < len(kinds):
                kind = kinds[i]
                step["step_kind"] = kind
        elif mode_key == "learn_syllabus_build":
            kinds = (
                _LEARN_SYLLABUS_WEB_STEP_KINDS
                if learn_syllabus_web
                else _LEARN_SYLLABUS_STEP_KINDS
            )
            if total_steps >= len(kinds) and i < len(kinds):
                kind = kinds[i]
                step["step_kind"] = kind
        elif kind not in STEP_KINDS:
            kind = infer_step_kind(desc, mode_key if mode != "code" else "code", i, total_steps)
            step["step_kind"] = kind
            notes.append(f"Step {i + 1}: inferred step_kind={kind}.")

        clean_desc, desc_modified = sanitize_step_description(
            desc,
            step_kind=kind,
            step_index=i,
            total_steps=total_steps,
        )
        if desc_modified:
            step["description"] = clean_desc
            notes.append(f"Step {i + 1}: sanitized step description.")
        else:
            step["description"] = clean_desc

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
    if mode_key == "character_build" and persona_research_lore:
        min_steps = len(_CHARACTER_BUILD_LORE_STEP_KINDS)
    if mode_key == "learn_syllabus_build":
        min_steps = (
            len(_LEARN_SYLLABUS_WEB_STEP_KINDS)
            if learn_syllabus_web
            else len(_LEARN_SYLLABUS_STEP_KINDS)
        )
    if mode_key == "character_build" and len(steps) != min_steps:
        plan, expand_note = expand_character_build_plan(
            plan, user_request, persona_research_lore=persona_research_lore
        )
        notes.append(expand_note)
        steps = plan["steps"]
        total_steps = len(steps)
        kinds = (
            _CHARACTER_BUILD_LORE_STEP_KINDS
            if persona_research_lore
            else _CHARACTER_BUILD_STEP_KINDS
        )
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            kind = kinds[i] if i < len(kinds) else "code"
            step["step_kind"] = kind
            step["max_iterations"] = _clamp_budget(kind, step.get("max_iterations"))
            if step.get("status") is None:
                step["status"] = "pending"

    if mode_key == "learn_syllabus_build" and len(steps) != min_steps:
        plan, expand_note = expand_learn_syllabus_plan(
            plan, user_request, learn_syllabus_web=learn_syllabus_web
        )
        notes.append(expand_note)
        steps = plan["steps"]
        total_steps = len(steps)
        kinds = (
            _LEARN_SYLLABUS_WEB_STEP_KINDS
            if learn_syllabus_web
            else _LEARN_SYLLABUS_STEP_KINDS
        )
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            kind = kinds[i] if i < len(kinds) else "code"
            step["step_kind"] = kind
            step["max_iterations"] = _clamp_budget(kind, step.get("max_iterations"))
            if step.get("status") is None:
                step["status"] = "pending"

    if mode_key == "research" and len(steps) < min_steps:
        plan, expand_note = expand_research_plan(
            plan, user_request, explore_brief_ran=explore_brief_ran
        )
        notes.append(expand_note)
        steps = plan["steps"]
        total_steps = len(steps)
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            desc = step.get("description", "")
            kind = step.get("step_kind")
            if kind not in STEP_KINDS:
                kind = infer_step_kind(desc, mode_key, i, total_steps)
                step["step_kind"] = kind
            step["max_iterations"] = _clamp_budget(kind, step.get("max_iterations"))
            if step.get("status") is None:
                step["status"] = "pending"

    if mode == "code" and user_request:
        try:
            from recon_policy import expand_code_documentation_plan

            plan, doc_note = expand_code_documentation_plan(plan, user_request)
            if doc_note:
                notes.append(doc_note)
                steps = plan.get("steps") or []
        except ImportError:
            pass
        req_lower = user_request.lower()
        if any(kw in req_lower for kw in TDD_KEYWORDS) and len(steps) < 4:
            notes.append(
                "Code TDD workflow recommended: explore → tdd_red → tdd_green → verify → finalize."
            )

    plan.setdefault("status", "in_progress")
    plan.setdefault("current_step_index", 0)
    return plan, notes


def tune_plan_json(
    plan_json: str,
    mode: str,
    user_request: str = "",
    *,
    explore_brief_ran: bool = False,
) -> tuple[str, list[str]]:
    """Parse JSON plan string, tune, return serialized JSON and notes."""
    plan = json.loads(plan_json)
    tuned, notes = validate_and_tune_plan(
        plan, mode, user_request, explore_brief_ran=explore_brief_ran
    )
    return json.dumps(tuned, indent=2), notes
