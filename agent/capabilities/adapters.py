"""Step-kind to capability mapping for capability-act modes."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Living plan checklist caps (shared across capability modes)
# ---------------------------------------------------------------------------

PLAN_CHECKLIST_CAP_IDS = frozenset({
    "cap.plan.update_checklist@v1",
    "cap.plan.read_implementation@v1",
})
_PLAN_CHECKLIST_CAPS = PLAN_CHECKLIST_CAP_IDS


def _with_plan_caps(base: frozenset[str]) -> frozenset[str]:
    return frozenset(set(base) | set(_PLAN_CHECKLIST_CAPS))


# ---------------------------------------------------------------------------
# Research (online / offline)
# ---------------------------------------------------------------------------

STEP_KIND_DEFAULT_CAPABILITY: dict[str, str] = {
    "explore": "cap.research.explore_brief@v1",
    "search": "cap.research.gather_web_sources@v1",
    "read": "cap.research.gather_web_sources@v1",
    "work": "cap.research.gather_web_sources@v1",
    "synthesize": "cap.research.synthesize_notes@v1",
    "finalize": "cap.research.finalize_deliverable@v1",
}

OFFLINE_STEP_KIND_DEFAULT_CAPABILITY: dict[str, str] = {
    "read": "cap.research.ingest_offline@v1",
    "work": "cap.research.ingest_offline@v1",
    "synthesize": "cap.research.synthesize_notes@v1",
    "finalize": "cap.research.finalize_deliverable@v1",
}

STEP_CAPABILITY_ALLOWLIST: dict[str, frozenset[str]] = {
    "explore": frozenset({"cap.research.explore_brief@v1"}),
    "search": frozenset({
        "cap.research.gather_web_sources@v1",
        "cap.web.search@v1",
    }),
    "read": frozenset({
        "cap.research.gather_web_sources@v1",
        "cap.web.read_pages@v1",
        "cap.research.append_note@v1",
    }),
    "work": _with_plan_caps(frozenset({
        "cap.research.gather_web_sources@v1",
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
        "cap.research.read_notes@v1",
    })),
    "synthesize": _with_plan_caps(frozenset({
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
        "cap.research.read_notes@v1",
    })),
    "finalize": frozenset({
        "cap.research.compile_report@v1",
        "cap.research.finalize_deliverable@v1",
    }),
}

OFFLINE_STEP_CAPABILITY_ALLOWLIST: dict[str, frozenset[str]] = {
    "read": frozenset({
        "cap.research.ingest_offline@v1",
        "cap.research.append_note@v1",
    }),
    "work": _with_plan_caps(frozenset({
        "cap.research.ingest_offline@v1",
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
        "cap.research.read_notes@v1",
    })),
    "synthesize": _with_plan_caps(frozenset({
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
    })),
    "finalize": frozenset({
        "cap.research.compile_report@v1",
        "cap.research.finalize_deliverable@v1",
    }),
}

TEMPLATE_CAPABILITY_STEPS: list[tuple[str, str]] = [
    ("search", "cap.research.gather_web_sources@v1"),
    ("read", "cap.research.gather_web_sources@v1"),
    ("synthesize", "cap.research.synthesize_notes@v1"),
    ("finalize", "cap.research.finalize_deliverable@v1"),
]

OFFLINE_TEMPLATE_CAPABILITY_STEPS: list[tuple[str, str]] = [
    ("read", "cap.research.ingest_offline@v1"),
    ("synthesize", "cap.research.synthesize_notes@v1"),
    ("finalize", "cap.research.finalize_deliverable@v1"),
]

DYNAMIC_TEMPLATE_CAPABILITY_STEPS: list[tuple[str, str]] = [
    ("work", "cap.research.gather_web_sources@v1"),
    ("finalize", "cap.research.finalize_deliverable@v1"),
]

OFFLINE_DYNAMIC_TEMPLATE_CAPABILITY_STEPS: list[tuple[str, str]] = [
    ("work", "cap.research.ingest_offline@v1"),
    ("finalize", "cap.research.finalize_deliverable@v1"),
]

# ---------------------------------------------------------------------------
# Character build (persona)
# ---------------------------------------------------------------------------

PERSONA_STEP_KIND_DEFAULT: dict[str, str] = {
    "search": "cap.persona.gather_lore@v1",
    "read": "cap.persona.ingest_sources@v1",
    "synthesize": "cap.persona.write_initialization@v1",
    "finalize": "cap.persona.finalize@v1",
}

PERSONA_LORE_STEP_KIND_DEFAULT: dict[str, str] = dict(PERSONA_STEP_KIND_DEFAULT)

PERSONA_STEP_ALLOWLIST: dict[str, frozenset[str]] = {
    "search": frozenset({"cap.persona.gather_lore@v1"}),
    "read": frozenset({"cap.persona.ingest_sources@v1"}),
    "synthesize": _with_plan_caps(frozenset({"cap.persona.write_initialization@v1"})),
    "finalize": frozenset({"cap.persona.finalize@v1"}),
}

PERSONA_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("read", "cap.persona.ingest_sources@v1"),
    ("synthesize", "cap.persona.write_initialization@v1"),
    ("finalize", "cap.persona.finalize@v1"),
]

PERSONA_LORE_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("search", "cap.persona.gather_lore@v1"),
    ("read", "cap.persona.ingest_sources@v1"),
    ("synthesize", "cap.persona.write_initialization@v1"),
    ("finalize", "cap.persona.finalize@v1"),
]

# ---------------------------------------------------------------------------
# Learn syllabus build
# ---------------------------------------------------------------------------

LEARN_STEP_KIND_DEFAULT: dict[str, str] = {
    "search": "cap.learn.gather_topic_sources@v1",
    "read": "cap.learn.ingest_course_materials@v1",
    "synthesize": "cap.learn.write_syllabus@v1",
    "finalize": "cap.learn.finalize_course@v1",
}

LEARN_STEP_ALLOWLIST: dict[str, frozenset[str]] = {
    "search": frozenset({"cap.learn.gather_topic_sources@v1"}),
    "read": frozenset({"cap.learn.ingest_course_materials@v1"}),
    # Synthesize is write-only — assessments are optional after a successful write
    # (kept off the schema so the model does not invent fake read_* caps).
    "synthesize": _with_plan_caps(frozenset({"cap.learn.write_syllabus@v1"})),
    "finalize": frozenset({"cap.learn.finalize_course@v1"}),
}

LEARN_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("read", "cap.learn.ingest_course_materials@v1"),
    ("synthesize", "cap.learn.write_syllabus@v1"),
    ("finalize", "cap.learn.finalize_course@v1"),
]

LEARN_WEB_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("search", "cap.learn.gather_topic_sources@v1"),
    ("read", "cap.learn.ingest_course_materials@v1"),
    ("synthesize", "cap.learn.write_syllabus@v1"),
    ("finalize", "cap.learn.finalize_course@v1"),
]

# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

WRITING_STEP_KIND_DEFAULT: dict[str, str] = {
    "read": "cap.writing.ingest_sources@v1",
    "write": "cap.writing.draft_sections@v1",
    "work": "cap.writing.draft_sections@v1",
    "finalize": "cap.writing.finalize_deliverable@v1",
}

WRITING_STEP_ALLOWLIST: dict[str, frozenset[str]] = {
    "read": frozenset({"cap.writing.ingest_sources@v1"}),
    "write": _with_plan_caps(frozenset({
        "cap.writing.init_document@v1",
        "cap.writing.draft_sections@v1",
        "cap.writing.read_outline@v1",
    })),
    "work": _with_plan_caps(frozenset({
        "cap.writing.init_document@v1",
        "cap.writing.draft_sections@v1",
        "cap.writing.read_outline@v1",
    })),
    "finalize": frozenset({
        "cap.writing.compile_document@v1",
        "cap.writing.finalize_deliverable@v1",
    }),
}

WRITING_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("work", "cap.writing.init_document@v1"),
    ("work", "cap.writing.draft_sections@v1"),
    ("finalize", "cap.writing.finalize_deliverable@v1"),
]

WRITING_DYNAMIC_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("write", "cap.writing.draft_sections@v1"),
    ("finalize", "cap.writing.finalize_deliverable@v1"),
]

WRITING_SOURCES_DYNAMIC_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("read", "cap.writing.ingest_sources@v1"),
    ("write", "cap.writing.draft_sections@v1"),
    ("finalize", "cap.writing.finalize_deliverable@v1"),
]

# ---------------------------------------------------------------------------
# Code / Dev
# ---------------------------------------------------------------------------

_CODE_WORK_CAPS = _with_plan_caps(frozenset({
    "cap.dev.edit_apply@v1",
    "cap.dev.create_file@v1",
    "cap.dev.write_files@v1",
    "cap.dev.read_region@v1",
    "cap.dev.recon@v1",
    "cap.dev.run_tests@v1",
    "cap.dev.run_linter@v1",
    "cap.dev.write_docs@v1",
    "cap.dev.project_setup@v1",
    "cap.dev.sync_project@v1",
}))

CODE_STEP_KIND_DEFAULT: dict[str, str] = {
    # DEAD for LoopEngine — kept for MCP/compat introspection of old plan JSON only.
    "explore": "cap.dev.recon@v1",
    "read": "cap.dev.read_region@v1",
    "code": "cap.dev.edit_apply@v1",
    "work": "cap.dev.edit_apply@v1",
    "tdd_red": "cap.dev.create_file@v1",
    "tdd_green": "cap.dev.edit_apply@v1",
    "tdd_refactor": "cap.dev.edit_apply@v1",
    "verify": "cap.dev.run_tests@v1",
    "finalize": "cap.dev.sync_project@v1",
}

CODE_STEP_ALLOWLIST: dict[str, frozenset[str]] = {
    "explore": frozenset({
        "cap.dev.recon@v1",
        "cap.dev.read_region@v1",
        "cap.dev.project_setup@v1",
    }),
    "read": frozenset({
        "cap.dev.recon@v1",
        "cap.dev.read_region@v1",
        "cap.dev.project_setup@v1",
    }),
    "code": _CODE_WORK_CAPS,
    "work": _CODE_WORK_CAPS,
    "tdd_red": _with_plan_caps(frozenset({
        "cap.dev.create_file@v1",
        "cap.dev.write_files@v1",
    })),
    "tdd_green": _with_plan_caps(frozenset({
        "cap.dev.create_file@v1",
        "cap.dev.edit_apply@v1",
        "cap.dev.read_region@v1",
        "cap.dev.run_tests@v1",
    })),
    "tdd_refactor": _with_plan_caps(frozenset({
        "cap.dev.edit_apply@v1",
        "cap.dev.run_linter@v1",
        "cap.dev.run_tests@v1",
        "cap.dev.read_region@v1",
    })),
    "verify": _with_plan_caps(frozenset({
        "cap.dev.run_tests@v1",
        "cap.dev.run_linter@v1",
        "cap.dev.sync_project@v1",
    })),
    "finalize": frozenset({
        "cap.dev.sync_project@v1",
        "cap.dev.create_file@v1",
    }),
}

CODE_DYNAMIC_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("work", "cap.dev.edit_apply@v1"),
    ("finalize", "cap.dev.sync_project@v1"),
]

CODE_IMPLEMENT_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("explore", "cap.dev.recon@v1"),
    ("work", "cap.dev.edit_apply@v1"),
    ("finalize", "cap.dev.sync_project@v1"),
]

CODE_DOC_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("explore", "cap.dev.recon@v1"),
    ("read", "cap.dev.read_region@v1"),
    ("code", "cap.dev.write_docs@v1"),
    ("finalize", "cap.dev.sync_project@v1"),
]

CODE_TDD_TEMPLATE_STEPS: list[tuple[str, str]] = [
    ("explore", "cap.dev.recon@v1"),
    ("tdd_red", "cap.dev.create_file@v1"),
    ("tdd_green", "cap.dev.edit_apply@v1"),
    ("verify", "cap.dev.run_tests@v1"),
    ("finalize", "cap.dev.sync_project@v1"),
]


def default_capability_for_step(
    step_kind: str,
    *,
    mode: str = "research",
    offline: bool = False,
    has_attachments: bool = False,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> str | None:
    kind = (step_kind or "").strip().lower()
    mode_norm = (mode or "research").strip().lower()

    if mode_norm == "character_build":
        return PERSONA_STEP_KIND_DEFAULT.get(kind)
    if mode_norm == "learn_syllabus_build":
        return LEARN_STEP_KIND_DEFAULT.get(kind)
    if mode_norm == "writing":
        return WRITING_STEP_KIND_DEFAULT.get(kind)
    if mode_norm == "code":
        # DEAD: code uses code_agent.py
        return None

    use_offline = offline or (has_attachments and kind in ("read", "work"))
    table = (
        OFFLINE_STEP_KIND_DEFAULT_CAPABILITY
        if use_offline
        else STEP_KIND_DEFAULT_CAPABILITY
    )
    return table.get(kind)


def allowed_capabilities_for_step(
    step_kind: str,
    *,
    mode: str = "research",
    offline: bool = False,
    has_attachments: bool = False,
    is_final_step: bool = False,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> frozenset[str]:
    kind = (step_kind or "work").strip().lower()
    mode_norm = (mode or "research").strip().lower()
    if is_final_step or kind == "finalize":
        kind = "finalize"

    if mode_norm == "character_build":
        allowed = PERSONA_STEP_ALLOWLIST.get(kind)
        if allowed:
            return allowed
        return frozenset({"cap.persona.ingest_sources@v1"})

    if mode_norm == "learn_syllabus_build":
        allowed = LEARN_STEP_ALLOWLIST.get(kind)
        if allowed:
            return allowed
        return frozenset({"cap.learn.ingest_course_materials@v1"})

    if mode_norm == "writing":
        allowed = WRITING_STEP_ALLOWLIST.get(kind)
        if allowed:
            return allowed
        return frozenset({"cap.writing.draft_sections@v1"})

    if mode_norm == "code":
        # DEAD: code uses code_agent.py — no LoopEngine capability allowlists.
        return frozenset()

    if offline:
        table = OFFLINE_STEP_CAPABILITY_ALLOWLIST
    elif has_attachments and kind in ("read", "work"):
        online = STEP_CAPABILITY_ALLOWLIST.get(kind, frozenset())
        offline_caps = OFFLINE_STEP_CAPABILITY_ALLOWLIST.get(kind, frozenset())
        allowed = online | offline_caps
        if allowed:
            return allowed
        return frozenset({"cap.research.ingest_offline@v1"})
    else:
        table = STEP_CAPABILITY_ALLOWLIST
    allowed = table.get(kind)
    if allowed:
        return allowed
    return frozenset({"cap.research.gather_web_sources@v1"})


def attach_capability_ids_to_plan(
    plan: dict,
    *,
    offline: bool = False,
    mode: str = "research",
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> dict:
    """Ensure each step has capability_id derived from step_kind when missing."""
    steps = plan.get("steps") or []
    mode_norm = (mode or "research").strip().lower()
    if mode_norm == "character_build":
        defaults = PERSONA_STEP_KIND_DEFAULT
    elif mode_norm == "learn_syllabus_build":
        defaults = LEARN_STEP_KIND_DEFAULT
    elif mode_norm == "writing":
        defaults = WRITING_STEP_KIND_DEFAULT
    elif mode_norm == "code":
        defaults = CODE_STEP_KIND_DEFAULT
    else:
        defaults = (
            OFFLINE_STEP_KIND_DEFAULT_CAPABILITY
            if offline
            else STEP_KIND_DEFAULT_CAPABILITY
        )
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("capability_id"):
            continue
        kind = (step.get("step_kind") or "work").strip().lower()
        cap_id = defaults.get(kind)
        if cap_id:
            step["capability_id"] = cap_id
    plan["steps"] = steps
    return plan
