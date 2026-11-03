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
    "micro",
    "delegate",
    "work",
)

DELEGATE_MODES = frozenset({"research", "code", "writing", "task"})

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
    "micro": (2, 3, 4),
    "delegate": (1, 1, 2),
    "work": (8, 14, 24),
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
    ("delegate", ("delegate", "hand off", "handoff")),
    ("micro", ("quick", "simple", "single")),
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
    "micro": "Fast path: complete the objective in one compact step; avoid explore loops.",
    "delegate": "Autonomous delegation — OS runs target mode headlessly; no tools needed on this step.",
    "work": (
        "Dynamic work phase: interleave read, grep, edit, test, and notes as needed. "
        "Tools are not phase-locked. Call mark_objective_complete when milestones are met."
    ),
}

CAPABILITY_ACT_MODES = frozenset({
    "research",
    "character_build",
    "learn_syllabus_build",
    "writing",
    "code",
})

CAPABILITY_STEP_KIND_HINTS: dict[str, dict[str, str]] = {
    "research": {
        "explore": "Reconnaissance: survey sources before deeper research work.",
        "search": (
            "Gather sources via `cap.research.gather_web_sources@v1` (or plan capability_id)."
        ),
        "read": "Extract facts via research gather/ingest capabilities.",
        "synthesize": "Synthesize via `cap.research.synthesize_notes@v1` from scratchpad notes.",
        "finalize": (
            "Put full report in top-level `final_report`; call "
            "`cap.research.finalize_deliverable@v1`."
        ),
        "work": (
            "Interleave gather / append-note / synthesize capabilities; advance when milestones met."
        ),
    },
    "character_build": {
        "search": "Call `cap.persona.gather_lore@v1` once with a focused topic.",
        "read": "Call `cap.persona.ingest_sources@v1` once.",
        "synthesize": "Call `cap.persona.write_initialization@v1` with full markdown.",
        "finalize": "Call `cap.persona.finalize@v1` with greeting and tagline.",
    },
    "learn_syllabus_build": {
        "search": "Call `cap.learn.gather_topic_sources@v1` once with topic.",
        "read": "Call `cap.learn.ingest_course_materials@v1` once.",
        "synthesize": "Call `cap.learn.write_syllabus@v1` with full syllabus JSON.",
        "finalize": "Call `cap.learn.finalize_course@v1`.",
    },
    "writing": {
        "write": (
            "Call `cap.writing.init_document@v1` if needed, then "
            "`cap.writing.draft_sections@v1` with grouped subsections."
        ),
        "work": (
            "Call `cap.writing.init_document@v1` if needed, then "
            "`cap.writing.draft_sections@v1` with grouped subsections."
        ),
        "read": (
            "Ingest attached sources: call `cap.writing.ingest_sources@v1` once. "
            "Use SCRATCHPAD on the draft step."
        ),
        "finalize": (
            "Call `cap.writing.finalize_deliverable@v1` (compiles the draft). "
            "Do not invent capability IDs."
        ),
    },
    "code": {
        "explore": (
            "Call `cap.dev.recon@v1` (tree + outline). "
            "Optional `cap.dev.project_setup@v1` if no project buffer."
        ),
        "read": "Call `cap.dev.read_region@v1` or `cap.dev.recon@v1`.",
        "code": (
            "Call `cap.dev.edit_apply@v1` / `cap.dev.create_file@v1` "
            "(docs: `cap.dev.write_docs@v1`)."
        ),
        "work": (
            "Wide allowlist: edit/create/recon/tests/docs via `cap.dev.*`. "
            "Do not invent capability IDs."
        ),
        "tdd_red": "Create failing tests via `cap.dev.create_file@v1` / edit_apply.",
        "tdd_green": "Implement via `cap.dev.edit_apply@v1`; verify with `cap.dev.run_tests@v1`.",
        "tdd_refactor": "Refactor via edit_apply; lint and re-run tests.",
        "verify": "Call `cap.dev.run_tests@v1` / `cap.dev.run_linter@v1`.",
        "finalize": "Call `cap.dev.sync_project@v1`. Do not invent capability IDs.",
    },
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
TDD_FIRST_KEYWORDS = (
    "failing test",
    "failing tests",
    "tests first",
    "test first",
    "write failing",
    "tdd",
)

MAX_STEP_DESCRIPTION_CHARS = 600
_RESEARCH_STEP_KINDS = ("search", "read", "synthesize", "finalize")
_CHARACTER_BUILD_STEP_KINDS = ("read", "synthesize", "finalize")
_CHARACTER_BUILD_LORE_STEP_KINDS = ("search", "read", "synthesize", "finalize")
_LEARN_SYLLABUS_STEP_KINDS = ("read", "synthesize", "finalize")
_LEARN_SYLLABUS_WEB_STEP_KINDS = ("search", "read", "synthesize", "finalize")

from agent.core.plan_descriptions import (
    capability_step_body,
    capability_step_description,
    has_tool_leak,
    strip_planner_boilerplate,
    tool_leak_tokens_for_mode,
)

_RESEARCH_FALLBACK_DESCRIPTIONS: dict[str, str] = {
    "explore": "Reconnaissance: survey sources before deeper research work.",
    "search": "Gather web sources on the research topic.",
    "read": "Read and extract key facts from URLs or attachments.",
    "synthesize": "Synthesize findings into scratchpad notes.",
    "finalize": "Compile final report and finalize deliverable.",
    "write": "Draft the assigned writing section.",
    "code": "Implement or edit code for this step.",
    "verify": "Verify outputs (tests, grep, lint).",
    "work": "Research work: gather sources, ingest attachments, synthesize notes.",
}

# Default fallbacks (no NASA/.gov leakage for non-research modes)
_FALLBACK_DESCRIPTIONS: dict[str, str] = {
    "explore": "Reconnaissance: survey sources and codebase before deeper work.",
    "search": "Search the web for relevant sources on the topic.",
    "read": "Read and extract key facts from URLs or attachments.",
    "synthesize": "Compile findings into notes or deliverables.",
    "finalize": "Complete deliverables and finalize.",
    "write": "Draft the assigned writing section.",
    "code": "Implement or edit code for this step.",
    "verify": "Verify outputs (tests, grep, lint).",
}


def _character_build_template(
    persona_research_lore: bool,
) -> list[tuple[str, str]]:
    kinds = (
        _CHARACTER_BUILD_LORE_STEP_KINDS
        if persona_research_lore
        else _CHARACTER_BUILD_STEP_KINDS
    )
    return [
        (
            kind,
            capability_step_body(
                "character_build",
                kind,
                persona_research_lore=persona_research_lore,
            ),
        )
        for kind in kinds
    ]


def _learn_syllabus_template(learn_syllabus_web: bool) -> list[tuple[str, str]]:
    kinds = (
        _LEARN_SYLLABUS_WEB_STEP_KINDS
        if learn_syllabus_web
        else _LEARN_SYLLABUS_STEP_KINDS
    )
    return [
        (
            kind,
            capability_step_body(
                "learn_syllabus_build",
                kind,
                learn_syllabus_web=learn_syllabus_web,
            ),
        )
        for kind in kinds
    ]


def _build_research_step(
    kind: str,
    description: str,
    req: str,
    *,
    offline: bool,
    cap_by_kind: dict[str, str],
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """Build one plan step with capability_id and optional params."""
    from agent.capabilities.adapters import default_capability_for_step

    _, default, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
    step: dict[str, Any] = {
        "status": "pending",
        "description": description,
        "step_kind": kind,
        "max_iterations": max_iterations if max_iterations is not None else default,
    }
    cap_id = cap_by_kind.get(kind) or default_capability_for_step(
        kind, offline=offline
    )
    if cap_id:
        step["capability_id"] = cap_id
        if "gather" in cap_id or "ingest" in cap_id:
            step["params"] = {"topic": req}
    return step


def _attach_research_capabilities(
    plan: dict[str, Any],
    *,
    offline: bool = False,
) -> dict[str, Any]:
    from agent.capabilities.adapters import attach_capability_ids_to_plan

    return attach_capability_ids_to_plan(plan, offline=offline)


def mode_step_description(
    mode_key: str,
    step_kind: str,
    user_request: str = "",
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> str:
    """Canonical step description for a mode/kind pair (overwrites planner leakage)."""
    req = (user_request or "the task").strip()[:500]
    if mode_key in ("character_build", "learn_syllabus_build", "writing"):
        return capability_step_description(
            mode_key,
            step_kind,
            user_request,
            persona_research_lore=persona_research_lore,
            learn_syllabus_web=learn_syllabus_web,
        )
    if mode_key == "research":
        body = _RESEARCH_FALLBACK_DESCRIPTIONS.get(
            step_kind, _FALLBACK_DESCRIPTIONS.get(step_kind, f"Complete step: {req}")
        )
        if " Topic:" in body:
            return body
        return f"{body} Topic: {req}."
    body = _FALLBACK_DESCRIPTIONS.get(step_kind, f"Complete step: {req}")
    if " Topic:" in body:
        return body
    return f"{body} Topic: {req}."


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

    stripped = strip_planner_boilerplate(raw)
    cleaned = _collapse_comma_repetition(stripped)
    modified = stripped != raw or cleaned != stripped
    heavy_repetition = modified and len(raw) > 200 and len(cleaned) < len(raw) * 0.15

    if heavy_repetition or is_degenerate_description(cleaned):
        kind = step_kind or infer_step_kind(cleaned[:200], "research", step_index, total_steps)
        cleaned = _RESEARCH_FALLBACK_DESCRIPTIONS.get(
            kind, _FALLBACK_DESCRIPTIONS.get(kind, cleaned[:MAX_STEP_DESCRIPTION_CHARS])
        )
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


def get_step_kind_hint(step_kind: str, mode: str = "") -> str:
    mode_norm = (mode or "").strip().lower()
    kind = (step_kind or "").strip().lower()
    if mode_norm in CAPABILITY_ACT_MODES:
        table = CAPABILITY_STEP_KIND_HINTS.get(mode_norm, {})
        if kind in table:
            return table[kind]
        return (
            f"Complete {kind or 'step'} via capability; do not invent capability IDs."
        )
    return STEP_KIND_HINTS.get(
        kind, "Complete the objective efficiently; avoid duplicate tool calls."
    )


def _clamp_budget(step_kind: str, max_iterations: int | None) -> int:
    lo, default, hi = BUDGET_RUBRIC.get(step_kind, (3, 4, 6))
    value = default if max_iterations is None else int(max_iterations)
    return max(lo, min(hi, value))


def salvage_oversized_plan(plan: dict[str, Any], *, max_desc: int = 200) -> dict[str, Any]:
    """Trim bloated LLM planner fields (runaway descriptions, milestone essays)."""
    if not isinstance(plan, dict):
        return plan
    for key in ("user_goal", "approach_summary"):
        val = plan.get(key)
        if isinstance(val, str) and len(val) > 400:
            plan[key] = val[:397].rstrip() + "..."
    for key in ("assumptions", "risks"):
        items = plan.get(key)
        if isinstance(items, list):
            if len(items) > 5:
                items = items[:5]
            plan[key] = [str(x)[:120] for x in items]
    milestones = plan.get("milestones")
    if isinstance(milestones, list):
        if len(milestones) > 6:
            milestones = milestones[:6]
        for ms in milestones:
            if isinstance(ms, dict):
                for mk in ("label", "success_criteria"):
                    mv = ms.get(mk)
                    if isinstance(mv, str) and len(mv) > 160:
                        ms[mk] = mv[:157].rstrip() + "..."
        plan["milestones"] = milestones
    steps = plan.get("steps")
    if isinstance(steps, list):
        if len(steps) > 8:
            plan["steps"] = steps[:8]
            steps = plan["steps"]
        for step in steps:
            if not isinstance(step, dict):
                continue
            desc = step.get("description", "")
            if isinstance(desc, str) and len(desc) > max_desc:
                step["description"] = desc[: max_desc - 3].rstrip() + "..."
    return plan


def research_plan_min_steps(*, offline_research: bool = False) -> int:
    """Minimum step count the LLM planner should target for research mode."""
    try:
        from .loop_settings import dynamic_loop_enabled

        if dynamic_loop_enabled():
            return 2
    except ImportError:
        pass
    if offline_research:
        return 3
    return MODE_MIN_STEPS.get("research", 4)


def build_fallback_research_plan(
    user_request: str,
    *,
    explore_brief_ran: bool = False,
    offline_research: bool = False,
) -> tuple[dict[str, Any], str]:
    """Deterministic research plan when the LLM planner fails all retries."""
    from agent.functions.research import build_capability_plan_from_recipe, resolve_recipe

    try:
        from .loop_settings import dynamic_loop_enabled

        dynamic = dynamic_loop_enabled()
    except ImportError:
        dynamic = False

    recipe = resolve_recipe(
        user_request,
        offline=offline_research,
        dynamic_loop=dynamic,
    )
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        offline=offline_research,
        dynamic_loop=dynamic,
    )
    plan["planner_fallback"] = True
    plan["status"] = "in_progress"
    plan["current_step_index"] = 0
    if offline_research:
        plan["offline_research"] = True
    if dynamic:
        plan["dynamic_plan"] = True
    if explore_brief_ran:
        plan["explore_brief_ran"] = True
    _attach_research_capabilities(plan, offline=offline_research)
    from agent.core.implementation_plan import ensure_implementation_block

    ensure_implementation_block(plan, "research", user_request=user_request)
    return plan, f"Recipe fallback plan ({recipe.recipe_id})."


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
    from agent.capabilities.adapters import (
        TEMPLATE_CAPABILITY_STEPS,
        attach_capability_ids_to_plan,
        default_capability_for_step,
    )

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
            f"Gather web sources on: {req}.{brief_note}",
        ),
        (
            "read",
            f"Read and extract key facts from sources for: {req}.",
        ),
        (
            "synthesize",
            f"Synthesize findings into notes for: {req}.",
        ),
        (
            "finalize",
            f"Finalize deliverable report for: {req}.",
        ),
    ]

    new_steps: list[dict[str, Any]] = []
    cap_by_kind = dict(TEMPLATE_CAPABILITY_STEPS)
    for kind, desc in template:
        new_steps.append(
            _build_research_step(kind, desc, req, offline=False, cap_by_kind=cap_by_kind)
        )

    if original_desc and original_desc not in new_steps[0]["description"]:
        new_steps[0]["description"] += f" Prior planner note: {original_desc}"

    old_count = len(steps)
    plan["steps"] = new_steps
    attach_capability_ids_to_plan(plan, offline=False)
    note = f"Expanded research plan from {old_count} to {len(new_steps)} steps."
    if explore_brief_ran:
        note += " Explore brief already ran; template starts at search."
    return plan, note


def expand_dynamic_research_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    explore_brief_ran: bool = False,
) -> tuple[dict[str, Any], str]:
    """Two-step dynamic plan: work + finalize (no rigid search/read/synthesize pipeline)."""
    from agent.capabilities.adapters import DYNAMIC_TEMPLATE_CAPABILITY_STEPS

    req = (user_request or "the research topic").strip()[:500]
    brief = (
        " Explore brief already done — use attachments and prior context."
        if explore_brief_ran
        else ""
    )
    template: list[tuple[str, str]] = [
        (
            "work",
            f"Research work: gather sources, read, synthesize notes.{brief} Topic: {req}",
        ),
        (
            "finalize",
            f"Finalize deliverable report for: {req}",
        ),
    ]
    cap_by_kind = dict(DYNAMIC_TEMPLATE_CAPABILITY_STEPS)
    new_steps = [
        _build_research_step(
            kind,
            desc,
            req,
            offline=False,
            cap_by_kind=cap_by_kind,
            max_iterations=BUDGET_RUBRIC.get(kind, (3, 8, 12))[1],
        )
        for kind, desc in template
    ]
    for step in new_steps:
        step["focus"] = "research"
    plan["steps"] = new_steps
    plan["dynamic_plan"] = True
    _attach_research_capabilities(plan, offline=False)
    return plan, f"Dynamic research plan ({len(new_steps)} steps: work + finalize)."


def expand_offline_research_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    explore_brief_ran: bool = False,
) -> tuple[dict[str, Any], str]:
    """Offline research: ingest attachments/journal → synthesize notes → finalize report."""
    req = (user_request or "the research topic").strip()[:500]
    brief_note = (
        " (Prior context already loaded — distill attachments and journal.)"
        if explore_brief_ran
        else ""
    )
    template: list[tuple[str, str]] = [
        (
            "read",
            f"Ingest key facts from attachments and journal for: {req}.{brief_note}",
        ),
        (
            "synthesize",
            f"Synthesize offline findings into notes for: {req}.",
        ),
        (
            "finalize",
            f"Finalize deliverable report for: {req}.",
        ),
    ]
    from agent.capabilities.adapters import OFFLINE_TEMPLATE_CAPABILITY_STEPS

    cap_by_kind = dict(OFFLINE_TEMPLATE_CAPABILITY_STEPS)
    new_steps = [
        _build_research_step(kind, desc, req, offline=True, cap_by_kind=cap_by_kind)
        for kind, desc in template
    ]
    plan["steps"] = new_steps
    plan["offline_research"] = True
    _attach_research_capabilities(plan, offline=True)
    return plan, f"Offline research plan ({len(new_steps)} steps: read → synthesize → finalize)."


def expand_dynamic_offline_research_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    explore_brief_ran: bool = False,
) -> tuple[dict[str, Any], str]:
    """Two-step offline plan: work from attachments/journal only, then finalize."""
    req = (user_request or "the research topic").strip()[:500]
    brief = (
        " Prior context loaded."
        if explore_brief_ran
        else ""
    )
    template: list[tuple[str, str]] = [
        (
            "work",
            f"Offline research: ingest attachments and journal only — no web.{brief} Topic: {req}",
        ),
        (
            "finalize",
            f"Finalize deliverable report for: {req}",
        ),
    ]
    from agent.capabilities.adapters import OFFLINE_DYNAMIC_TEMPLATE_CAPABILITY_STEPS

    cap_by_kind = dict(OFFLINE_DYNAMIC_TEMPLATE_CAPABILITY_STEPS)
    new_steps = [
        _build_research_step(
            kind,
            desc,
            req,
            offline=True,
            cap_by_kind=cap_by_kind,
            max_iterations=BUDGET_RUBRIC.get(kind, (3, 8, 12))[1],
        )
        for kind, desc in template
    ]
    for step in new_steps:
        step["focus"] = "research"
    plan["steps"] = new_steps
    plan["dynamic_plan"] = True
    plan["offline_research"] = True
    _attach_research_capabilities(plan, offline=True)
    return plan, f"Dynamic offline research plan ({len(new_steps)} steps: work + finalize)."


def expand_dynamic_code_plan(
    plan: dict[str, Any],
    user_request: str,
) -> tuple[dict[str, Any], str]:
    from agent.capabilities.adapters import attach_capability_ids_to_plan

    template: list[tuple[str, str]] = [
        ("work", capability_step_description("code", "work", user_request)),
        ("finalize", capability_step_description("code", "finalize", user_request)),
    ]
    new_steps: list[dict[str, Any]] = []
    for kind, desc in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (4, 10, 16))
        new_steps.append({
            "status": "pending",
            "description": desc,
            "step_kind": kind,
            "focus": "implement",
            "max_iterations": default,
        })
    plan["steps"] = new_steps
    plan["dynamic_plan"] = True
    attach_capability_ids_to_plan(plan, mode="code")
    return plan, f"Dynamic code plan ({len(new_steps)} steps: work + finalize)."


def should_expand_tdd_code_plan(user_request: str) -> bool:
    low = (user_request or "").lower()
    return any(kw in low for kw in TDD_FIRST_KEYWORDS)


def expand_tdd_code_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    skip_explore: bool = False,
) -> tuple[dict[str, Any], str]:
    from agent.capabilities.adapters import CODE_TDD_TEMPLATE_STEPS

    low = (user_request or "").lower()
    template = list(CODE_TDD_TEMPLATE_STEPS)
    if skip_explore or "tiny" in low or "from scratch" in low or "only:" in low:
        template = [step for step in template if step[0] != "explore"]
    new_steps: list[dict[str, Any]] = []
    for kind, cap_id in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (4, 10, 16))
        new_steps.append({
            "status": "pending",
            "description": capability_step_description("code", kind, user_request),
            "step_kind": kind,
            "capability_id": cap_id,
            "focus": "implement" if kind.startswith("tdd") else kind,
            "max_iterations": default,
        })
    plan["steps"] = new_steps
    plan["dynamic_plan"] = True
    explore_note = " (no explore)" if len(template) < len(CODE_TDD_TEMPLATE_STEPS) else ""
    return plan, f"Dynamic TDD code plan ({len(new_steps)} steps{explore_note})."


def expand_dynamic_writing_plan(
    plan: dict[str, Any],
    user_request: str,
    *,
    has_attachments: bool = False,
    writing_brief: dict | None = None,
) -> tuple[dict[str, Any], str]:
    from agent.functions.writing_brief import WritingBrief

    brief = WritingBrief.from_plan_dict(writing_brief)
    use_sources = has_attachments or (brief is not None and brief.scope == "from_sources")
    if use_sources:
        template: list[tuple[str, str]] = [
            ("read", capability_step_description("writing", "read", user_request, writing_brief=writing_brief)),
            ("work", capability_step_description("writing", "work", user_request, writing_brief=writing_brief)),
            ("finalize", capability_step_description("writing", "finalize", user_request, writing_brief=writing_brief)),
        ]
        caps = {
            "read": "cap.writing.ingest_sources@v1",
            "work": "cap.writing.draft_sections@v1",
            "write": "cap.writing.draft_sections@v1",
            "finalize": "cap.writing.finalize_deliverable@v1",
        }
    else:
        template = [
            ("work", capability_step_description("writing", "work", user_request, writing_brief=writing_brief)),
            ("finalize", capability_step_description("writing", "finalize", user_request, writing_brief=writing_brief)),
        ]
        caps = {
            "work": "cap.writing.draft_sections@v1",
            "write": "cap.writing.draft_sections@v1",
            "finalize": "cap.writing.finalize_deliverable@v1",
        }
    new_steps: list[dict[str, Any]] = []
    work_budget = 6
    if brief and brief.advance_when == "scope_met":
        work_budget = 10
    for kind, desc in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (4, 6, 8))
        budget = work_budget if kind in ("work", "write") and brief else default
        new_steps.append({
            "status": "pending",
            "description": desc,
            "step_kind": kind,
            "focus": "write" if kind != "read" else "read",
            "capability_id": caps[kind],
            "max_iterations": budget,
        })
    plan["steps"] = new_steps
    plan["dynamic_plan"] = True
    if writing_brief:
        plan["writing_brief"] = writing_brief
    label = "with sources" if use_sources else f"{len(new_steps)} steps"
    return plan, f"Dynamic writing plan ({label})."


def _apply_capability_descriptions_to_plan(
    plan: dict[str, Any],
    mode: str,
    user_request: str,
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
    writing_brief: dict | None = None,
) -> None:
    """Overwrite step descriptions with canonical capability-first copy."""
    for step in plan.get("steps") or []:
        if not isinstance(step, dict):
            continue
        kind = (step.get("step_kind") or "work").strip().lower()
        if mode == "writing":
            step["description"] = capability_step_description(
                mode,
                kind,
                user_request,
                writing_brief=writing_brief or plan.get("writing_brief"),
            )
        else:
            step["description"] = mode_step_description(
                mode,
                kind,
                user_request,
                persona_research_lore=persona_research_lore,
                learn_syllabus_web=learn_syllabus_web,
            )


def build_fallback_persona_plan(
    user_request: str,
    *,
    persona_research_lore: bool = False,
) -> tuple[dict[str, Any], str]:
    """Deterministic persona plan when the LLM planner fails all retries."""
    from agent.functions.persona import build_capability_plan_from_recipe, resolve_recipe

    recipe = resolve_recipe(persona_research_lore=persona_research_lore)
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        persona_research_lore=persona_research_lore,
    )
    _apply_capability_descriptions_to_plan(
        plan,
        "character_build",
        user_request,
        persona_research_lore=persona_research_lore,
    )
    plan["planner_fallback"] = True
    plan["status"] = "in_progress"
    plan["current_step_index"] = 0
    from agent.core.implementation_plan import ensure_implementation_block

    ensure_implementation_block(plan, "character_build", user_request=user_request)
    return plan, f"Recipe fallback plan ({recipe.recipe_id})."


def build_fallback_learn_plan(
    user_request: str,
    *,
    learn_syllabus_web: bool = False,
) -> tuple[dict[str, Any], str]:
    """Deterministic learn syllabus plan when the LLM planner fails all retries."""
    from agent.functions.learn import build_capability_plan_from_recipe, resolve_recipe

    recipe = resolve_recipe(learn_syllabus_web=learn_syllabus_web)
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        learn_syllabus_web=learn_syllabus_web,
    )
    _apply_capability_descriptions_to_plan(
        plan,
        "learn_syllabus_build",
        user_request,
        learn_syllabus_web=learn_syllabus_web,
    )
    plan["planner_fallback"] = True
    plan["status"] = "in_progress"
    plan["current_step_index"] = 0
    from agent.core.implementation_plan import ensure_implementation_block

    ensure_implementation_block(plan, "learn_syllabus_build", user_request=user_request)
    return plan, f"Recipe fallback plan ({recipe.recipe_id})."


def build_fallback_writing_plan(
    user_request: str,
    *,
    dynamic_loop: bool = True,
    has_attachments: bool = False,
    writing_brief: dict | None = None,
) -> tuple[dict[str, Any], str]:
    """Deterministic writing plan when the LLM planner fails all retries."""
    from agent.functions.writing import build_capability_plan_from_recipe, resolve_recipe

    recipe = resolve_recipe(
        dynamic_loop=dynamic_loop,
        has_attachments=has_attachments,
        writing_brief=writing_brief,
    )
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        dynamic_loop=dynamic_loop,
        has_attachments=has_attachments,
        writing_brief=writing_brief,
    )
    _apply_capability_descriptions_to_plan(plan, "writing", user_request, writing_brief=writing_brief)
    if writing_brief:
        plan["writing_brief"] = writing_brief
    plan["planner_fallback"] = True
    plan["status"] = "in_progress"
    plan["current_step_index"] = 0
    from agent.core.implementation_plan import ensure_implementation_block

    ensure_implementation_block(plan, "writing", user_request=user_request)
    return plan, f"Recipe fallback plan ({recipe.recipe_id})."


def build_fallback_code_plan(
    user_request: str,
    *,
    dynamic_loop: bool = True,
    documentation: bool = False,
    tdd: bool = False,
) -> tuple[dict[str, Any], str]:
    """Deterministic code plan when the LLM planner fails all retries."""
    from agent.functions.code import build_capability_plan_from_recipe, resolve_recipe

    recipe = resolve_recipe(
        dynamic_loop=dynamic_loop,
        documentation=documentation,
        tdd=tdd,
    )
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        dynamic_loop=dynamic_loop,
        documentation=documentation,
        tdd=tdd,
    )
    _apply_capability_descriptions_to_plan(plan, "code", user_request)
    plan["planner_fallback"] = True
    plan["status"] = "in_progress"
    plan["current_step_index"] = 0
    from agent.core.implementation_plan import ensure_implementation_block

    ensure_implementation_block(plan, "code", user_request=user_request)
    return plan, f"Recipe fallback plan ({recipe.recipe_id})."


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

    from agent.functions.persona import build_capability_plan_from_recipe, resolve_recipe

    recipe = resolve_recipe(persona_research_lore=persona_research_lore)
    old_count = len(steps)
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        persona_research_lore=persona_research_lore,
    )
    _apply_capability_descriptions_to_plan(
        plan,
        "character_build",
        user_request,
        persona_research_lore=persona_research_lore,
    )
    new_steps = plan.get("steps") or []
    if original_desc and new_steps and original_desc not in new_steps[0].get("description", ""):
        new_steps[0]["description"] += f" Prior planner note: {original_desc}"

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
    original_desc = ""
    if steps and isinstance(steps[0], dict):
        original_desc = str(steps[0].get("description", "")).strip()[:400]

    from agent.functions.learn import build_capability_plan_from_recipe, resolve_recipe

    recipe = resolve_recipe(learn_syllabus_web=learn_syllabus_web)
    old_count = len(steps)
    plan = build_capability_plan_from_recipe(
        recipe,
        user_request,
        learn_syllabus_web=learn_syllabus_web,
    )
    _apply_capability_descriptions_to_plan(
        plan,
        "learn_syllabus_build",
        user_request,
        learn_syllabus_web=learn_syllabus_web,
    )
    new_steps = plan.get("steps") or []
    if original_desc and new_steps and original_desc not in new_steps[0].get("description", ""):
        new_steps[0]["description"] += f" Prior planner note: {original_desc}"

    plan["current_step_index"] = 0
    plan["status"] = "in_progress"
    note = f"Expanded learn_syllabus_build plan from {old_count} to {len(new_steps)} steps."
    return plan, note


def validate_and_tune_plan(
    plan: dict[str, Any],
    mode: str,
    user_request: str = "",
    *,
    explore_brief_ran: bool = False,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
    offline_research: bool = False,
    has_attachments: bool = False,
    writing_brief: dict | None = None,
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

        if mode_key in ("character_build", "learn_syllabus_build") and kind:
            canonical = mode_step_description(
                mode_key,
                kind,
                user_request,
                persona_research_lore=persona_research_lore,
                learn_syllabus_web=learn_syllabus_web,
            )
            nasa_leak = any(
                token in (step.get("description") or "").lower()
                for token in ("nasa", ".gov", ".edu", "authoritative web")
            )
            if nasa_leak or step.get("description") != canonical:
                step["description"] = canonical
                notes.append(f"Step {i + 1}: applied {mode_key} description for {kind}.")

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
            step["description"] = mode_step_description(
                mode_key,
                kind,
                user_request,
                persona_research_lore=persona_research_lore,
            )
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
            step["description"] = mode_step_description(
                mode_key,
                kind,
                user_request,
                learn_syllabus_web=learn_syllabus_web,
            )
            step["max_iterations"] = _clamp_budget(kind, step.get("max_iterations"))
            if step.get("status") is None:
                step["status"] = "pending"

    if mode_key == "research" and len(steps) < min_steps:
        try:
            from .loop_settings import dynamic_loop_enabled

            if offline_research:
                if dynamic_loop_enabled():
                    plan, expand_note = expand_dynamic_offline_research_plan(
                        plan, user_request, explore_brief_ran=explore_brief_ran
                    )
                else:
                    plan, expand_note = expand_offline_research_plan(
                        plan, user_request, explore_brief_ran=explore_brief_ran
                    )
            elif dynamic_loop_enabled():
                plan, expand_note = expand_dynamic_research_plan(
                    plan, user_request, explore_brief_ran=explore_brief_ran
                )
            else:
                plan, expand_note = expand_research_plan(
                    plan, user_request, explore_brief_ran=explore_brief_ran
                )
        except ImportError:
            if offline_research:
                plan, expand_note = expand_offline_research_plan(
                    plan, user_request, explore_brief_ran=explore_brief_ran
                )
            else:
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

    if mode_key == "writing" and len(steps) < min_steps:
        try:
            from .loop_settings import dynamic_loop_enabled

            if dynamic_loop_enabled():
                plan, expand_note = expand_dynamic_writing_plan(
                    plan, user_request, has_attachments=has_attachments, writing_brief=writing_brief
                )
                notes.append(expand_note)
                steps = plan["steps"]
                total_steps = len(steps)
        except ImportError:
            pass

    if mode == "code" and user_request:
        try:
            from agent.core.code_scaffolds import is_habit_tracker_goal

            habit_micro = bool(plan.get("micro_plan")) and is_habit_tracker_goal(
                user_request
            )
        except ImportError:
            habit_micro = False
        try:
            from .loop_settings import dynamic_loop_enabled

            if not habit_micro:
                if should_expand_tdd_code_plan(user_request) and len(steps) < 4:
                    plan, tdd_note = expand_tdd_code_plan(plan, user_request)
                    notes.append(tdd_note)
                    steps = plan.get("steps") or []
                elif dynamic_loop_enabled() and len(steps) < 3:
                    plan, dyn_note = expand_dynamic_code_plan(plan, user_request)
                    notes.append(dyn_note)
                    steps = plan.get("steps") or []
        except ImportError:
            pass
        try:
            from agent.policies import expand_code_documentation_plan

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

    if mode_key == "research":
        effective_offline = offline_research or bool(plan.get("offline_research"))
        _attach_research_capabilities(plan, offline=effective_offline)
        tool_leak_tokens = tool_leak_tokens_for_mode("research")
        for step in plan.get("steps") or []:
            if not isinstance(step, dict):
                continue
            kind = (step.get("step_kind") or "work").strip().lower()
            desc_lower = (step.get("description") or "").lower()
            if has_tool_leak(step.get("description") or "", tool_leak_tokens):
                step["description"] = mode_step_description("research", kind, user_request)
                notes.append(f"Step: replaced tool-language description for {kind}.")
        try:
            from agent.functions.research import resolve_recipe

            dynamic = False
            try:
                from .loop_settings import dynamic_loop_enabled

                dynamic = dynamic_loop_enabled()
            except ImportError:
                pass
            recipe = resolve_recipe(
                user_request,
                offline=effective_offline,
                dynamic_loop=dynamic,
            )
            plan["capability_recipe"] = recipe.recipe_id
        except ImportError:
            pass

    if mode_key == "character_build":
        from agent.capabilities.adapters import attach_capability_ids_to_plan

        attach_capability_ids_to_plan(
            plan,
            mode="character_build",
            persona_research_lore=persona_research_lore,
        )
        try:
            from agent.functions.persona import resolve_recipe as resolve_persona_recipe

            recipe = resolve_persona_recipe(persona_research_lore=persona_research_lore)
            plan["capability_recipe"] = recipe.recipe_id
        except ImportError:
            pass
        tool_leak_tokens = tool_leak_tokens_for_mode("character_build")
        for step in plan.get("steps") or []:
            if not isinstance(step, dict):
                continue
            kind = (step.get("step_kind") or "work").strip().lower()
            if has_tool_leak(step.get("description") or "", tool_leak_tokens):
                step["description"] = mode_step_description(
                    "character_build",
                    kind,
                    user_request,
                    persona_research_lore=persona_research_lore,
                )
                notes.append(f"Step: replaced tool-language description for {kind}.")

    if mode_key == "learn_syllabus_build":
        from agent.capabilities.adapters import attach_capability_ids_to_plan

        attach_capability_ids_to_plan(
            plan,
            mode="learn_syllabus_build",
            learn_syllabus_web=learn_syllabus_web,
        )
        try:
            from agent.functions.learn import resolve_recipe as resolve_learn_recipe

            recipe = resolve_learn_recipe(learn_syllabus_web=learn_syllabus_web)
            plan["capability_recipe"] = recipe.recipe_id
        except ImportError:
            pass
        tool_leak_tokens = tool_leak_tokens_for_mode("learn_syllabus_build")
        for step in plan.get("steps") or []:
            if not isinstance(step, dict):
                continue
            kind = (step.get("step_kind") or "work").strip().lower()
            if has_tool_leak(step.get("description") or "", tool_leak_tokens):
                step["description"] = mode_step_description(
                    "learn_syllabus_build",
                    kind,
                    user_request,
                    learn_syllabus_web=learn_syllabus_web,
                )
                notes.append(f"Step: replaced tool-language description for {kind}.")

    if mode_key == "writing":
        from agent.capabilities.adapters import attach_capability_ids_to_plan

        if writing_brief:
            plan["writing_brief"] = writing_brief
            if writing_brief.get("has_attachments"):
                plan["writing_has_attachments"] = True
        attach_capability_ids_to_plan(plan, mode="writing")
        try:
            from agent.functions.writing import resolve_recipe as resolve_writing_recipe
            from .loop_settings import dynamic_loop_enabled

            recipe = resolve_writing_recipe(
                dynamic_loop=dynamic_loop_enabled(),
                has_attachments=has_attachments or bool(plan.get("writing_has_attachments")),
                writing_brief=writing_brief or plan.get("writing_brief"),
            )
            plan["capability_recipe"] = recipe.recipe_id
        except ImportError:
            try:
                from agent.functions.writing import resolve_recipe as resolve_writing_recipe

                recipe = resolve_writing_recipe(dynamic_loop=True)
                plan["capability_recipe"] = recipe.recipe_id
            except ImportError:
                pass
        tool_leak_tokens = tool_leak_tokens_for_mode("writing")
        for step in plan.get("steps") or []:
            if not isinstance(step, dict):
                continue
            kind = (step.get("step_kind") or "work").strip().lower()
            if has_tool_leak(step.get("description") or "", tool_leak_tokens):
                step["description"] = mode_step_description(
                    "writing",
                    kind,
                    user_request,
                )
                notes.append(f"Step: replaced tool-language description for {kind}.")
            brief_for_desc = writing_brief or plan.get("writing_brief")
            if brief_for_desc and kind in ("work", "write", "read", "finalize"):
                step["description"] = capability_step_description(
                    "writing",
                    kind,
                    user_request,
                    writing_brief=brief_for_desc,
                )

    if mode_key == "code":
        from agent.capabilities.adapters import attach_capability_ids_to_plan

        attach_capability_ids_to_plan(plan, mode="code")
        try:
            from agent.functions.code import resolve_recipe as resolve_code_recipe
            from agent.policies.recon_policy import is_documentation_task
            from .loop_settings import dynamic_loop_enabled

            recipe = resolve_code_recipe(
                dynamic_loop=dynamic_loop_enabled(),
                documentation=is_documentation_task(user_request),
            )
            plan["capability_recipe"] = recipe.recipe_id
        except ImportError:
            pass
        tool_leak_tokens = tool_leak_tokens_for_mode("code")
        for step in plan.get("steps") or []:
            if not isinstance(step, dict):
                continue
            kind = (step.get("step_kind") or "work").strip().lower()
            if has_tool_leak(step.get("description") or "", tool_leak_tokens):
                step["description"] = capability_step_description(
                    "code",
                    kind,
                    user_request,
                )
                notes.append(f"Step: replaced tool-language description for {kind}.")

    from agent.core.implementation_plan import (
        ensure_implementation_block,
        should_write_living_plan,
    )

    if should_write_living_plan(plan, mode_key):
        ensure_implementation_block(plan, mode_key, user_request=user_request)

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
