"""Step-kind to capability mapping for research act loop."""
from __future__ import annotations

# Default capability per legacy step_kind (online research)
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

# Allowed capabilities per step for LLM schema (subset)
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
    "work": frozenset({
        "cap.research.gather_web_sources@v1",
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
        "cap.research.read_notes@v1",
    }),
    "synthesize": frozenset({
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
        "cap.research.read_notes@v1",
    }),
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
    "work": frozenset({
        "cap.research.ingest_offline@v1",
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
        "cap.research.read_notes@v1",
    }),
    "synthesize": frozenset({
        "cap.research.synthesize_notes@v1",
        "cap.research.append_note@v1",
    }),
    "finalize": frozenset({
        "cap.research.compile_report@v1",
        "cap.research.finalize_deliverable@v1",
    }),
}

# Template plans: step_kind -> capability_id
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


def default_capability_for_step(
    step_kind: str,
    *,
    offline: bool = False,
    has_attachments: bool = False,
) -> str | None:
    kind = (step_kind or "").strip().lower()
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
    offline: bool = False,
    has_attachments: bool = False,
    is_final_step: bool = False,
) -> frozenset[str]:
    kind = (step_kind or "work").strip().lower()
    if is_final_step or kind == "finalize":
        kind = "finalize"
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


def attach_capability_ids_to_plan(plan: dict, *, offline: bool = False) -> dict:
    """Ensure each step has capability_id derived from step_kind when missing."""
    steps = plan.get("steps") or []
    defaults = OFFLINE_STEP_KIND_DEFAULT_CAPABILITY if offline else STEP_KIND_DEFAULT_CAPABILITY
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
