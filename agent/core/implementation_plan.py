"""Living implementation plan (design plane) helpers — Antigravity-style artifacts."""
from __future__ import annotations

import re
from typing import Any

LIVING_PLAN_MODES = frozenset({
    "code",
    "writing",
    "research",
    "learn_syllabus_build",
    "character_build",
})

_PLAN_CAPS = frozenset({
    "cap.plan.update_checklist@v1",
    "cap.plan.read_implementation@v1",
})


def living_plan_modes() -> frozenset[str]:
    return LIVING_PLAN_MODES


def plan_checklist_capability_ids() -> frozenset[str]:
    return _PLAN_CAPS


def should_write_living_plan(plan: dict[str, Any], mode: str) -> bool:
    if (mode or "").strip().lower() not in LIVING_PLAN_MODES:
        return False
    if plan.get("micro_plan"):
        return False
    return True


def _slug_id(text: str, index: int) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    base = (raw[:40] or f"item-{index}")
    return f"{base}-{index}"


def _as_str_list(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if s:
            out.append(s[:240])
        if len(out) >= limit:
            break
    return out


def _normalize_checklist(raw: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return items
    for i, entry in enumerate(raw, 1):
        if isinstance(entry, str):
            text = entry.strip()
            if not text:
                continue
            items.append({"id": _slug_id(text, i), "text": text[:200], "status": "pending"})
            continue
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or entry.get("label") or "").strip()
        if not text:
            continue
        status = str(entry.get("status") or "pending").strip().lower()
        if status not in ("pending", "done", "skipped"):
            status = "pending"
        cid = str(entry.get("id") or "").strip() or _slug_id(text, i)
        items.append({"id": cid[:64], "text": text[:200], "status": status})
        if len(items) >= 12:
            break
    return items


def scaffold_implementation(
    *,
    mode: str,
    user_request: str = "",
    approach_summary: str = "",
    risks: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic design-plane block when the planner omits implementation."""
    mode_n = (mode or "").strip().lower()
    goal = (user_request or "").strip()[:400]
    approach = (approach_summary or "").strip()[:500]
    summary = approach or f"Execute the task: {goal[:200]}" if goal else "Execute the approved plan."
    acceptance: list[str] = []
    checklist: list[dict[str, str]] = []
    files_create: list[str] = []
    files_modify: list[str] = []
    testing = ""
    sections: list[str] = []
    deliverable = ""
    questions: list[str] = []
    source_strategy = ""
    modules: list[str] = []
    persona_axes: list[str] = []
    out_of_scope = ["Unrelated refactors outside the stated goal."]

    if mode_n == "code":
        acceptance = [
            "Required files exist in the project buffer/disk",
            "Tests pass when applicable",
            "Project synced if finalize runs",
        ]
        checklist = [
            {
                "id": "setup-1",
                "text": "Init project buffer once if empty (project_setup)",
                "status": "pending",
            },
            {
                "id": "tests-1",
                "text": "Write failing tests first (create_file / edit_apply)",
                "status": "pending",
            },
            {
                "id": "impl-1",
                "text": "Implement primary source until tests can pass",
                "status": "pending",
            },
            {
                "id": "test-1",
                "text": "Run tests / verify behavior",
                "status": "pending",
            },
            {
                "id": "docs-1",
                "text": "Update docs if required by the goal",
                "status": "pending",
            },
            {
                "id": "sync-1",
                "text": "Sync project to disk",
                "status": "pending",
            },
        ]
        testing = "Use project tests (pytest or equivalent) when the goal implies verification."
    elif mode_n == "writing":
        acceptance = [
            "Draft covers the planned sections",
            "Deliverable compiled/finalized",
        ]
        sections = ["Introduction", "Main body", "Conclusion"]
        checklist = [
            {"id": "outline-1", "text": "Confirm outline / sections", "status": "pending"},
            {"id": "draft-1", "text": "Draft primary sections", "status": "pending"},
            {"id": "revise-1", "text": "Tighten prose and structure", "status": "pending"},
            {"id": "final-1", "text": "Compile and finalize deliverable", "status": "pending"},
        ]
        deliverable = "deliverable.md"
    elif mode_n == "research":
        acceptance = [
            "Key questions answered with sources",
            "Notes synthesized",
            "Final report delivered",
        ]
        questions = [goal[:160]] if goal else ["What are the main findings?"]
        source_strategy = "Gather web or offline sources, then synthesize notes."
        checklist = [
            {"id": "q-1", "text": "Clarify research questions", "status": "pending"},
            {"id": "src-1", "text": "Gather primary sources", "status": "pending"},
            {"id": "note-1", "text": "Save and synthesize notes", "status": "pending"},
            {"id": "rep-1", "text": "Write and finalize report", "status": "pending"},
        ]
    elif mode_n == "learn_syllabus_build":
        acceptance = [
            "Syllabus structure written",
            "Course materials finalized",
        ]
        modules = ["Module 1 foundations", "Module 2 core skills", "Module 3 practice"]
        checklist = [
            {"id": "topic-1", "text": "Confirm course topic and scope", "status": "pending"},
            {"id": "ingest-1", "text": "Ingest or gather course materials", "status": "pending"},
            {"id": "syll-1", "text": "Write syllabus.json structure", "status": "pending"},
            {"id": "fin-1", "text": "Finalize course package", "status": "pending"},
        ]
    elif mode_n == "character_build":
        acceptance = [
            "initialization.md written with required sections",
            "Persona finalized with greeting/tagline",
        ]
        persona_axes = ["Voice", "Backstory", "Scene agency", "Boundaries"]
        checklist = [
            {"id": "lore-1", "text": "Gather or ingest lore/sources", "status": "pending"},
            {"id": "init-1", "text": "Write initialization.md", "status": "pending"},
            {"id": "fin-1", "text": "Finalize persona", "status": "pending"},
        ]
    else:
        acceptance = ["Task objective completed"]
        checklist = [
            {"id": "work-1", "text": "Complete primary work", "status": "pending"},
            {"id": "fin-1", "text": "Finalize deliverable", "status": "pending"},
        ]

    return {
        "summary": summary[:800],
        "acceptance": acceptance,
        "checklist": checklist,
        "out_of_scope": out_of_scope,
        "risks": list(risks or [])[:5],
        "files_create": files_create,
        "files_modify": files_modify,
        "testing_strategy": testing,
        "sections": sections,
        "deliverable_path": deliverable,
        "research_questions": questions,
        "source_strategy": source_strategy,
        "modules_outline": modules,
        "persona_axes": persona_axes,
    }


def ensure_implementation_block(
    plan: dict[str, Any],
    mode: str,
    *,
    user_request: str = "",
) -> dict[str, Any]:
    """Ensure plan['implementation'] exists and is normalized. Mutates and returns plan."""
    if not should_write_living_plan(plan, mode):
        return plan

    raw = plan.get("implementation")
    if not isinstance(raw, dict):
        raw = {}

    scaffold = scaffold_implementation(
        mode=mode,
        user_request=user_request or str(plan.get("user_goal") or ""),
        approach_summary=str(plan.get("approach_summary") or ""),
        risks=_as_str_list(plan.get("risks"), limit=5),
    )

    merged = dict(scaffold)
    for key, value in raw.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value

    merged["summary"] = str(merged.get("summary") or scaffold["summary"])[:800]
    merged["acceptance"] = _as_str_list(merged.get("acceptance"), limit=8) or scaffold["acceptance"]
    merged["out_of_scope"] = _as_str_list(merged.get("out_of_scope"), limit=6) or scaffold["out_of_scope"]
    merged["risks"] = _as_str_list(merged.get("risks"), limit=6) or scaffold["risks"]
    merged["files_create"] = _as_str_list(merged.get("files_create"), limit=12)
    merged["files_modify"] = _as_str_list(merged.get("files_modify"), limit=12)
    merged["testing_strategy"] = str(merged.get("testing_strategy") or "")[:500]
    merged["sections"] = _as_str_list(merged.get("sections"), limit=12)
    merged["deliverable_path"] = str(merged.get("deliverable_path") or "")[:200]
    merged["research_questions"] = _as_str_list(merged.get("research_questions"), limit=8)
    merged["source_strategy"] = str(merged.get("source_strategy") or "")[:400]
    merged["modules_outline"] = _as_str_list(merged.get("modules_outline"), limit=12)
    merged["persona_axes"] = _as_str_list(merged.get("persona_axes"), limit=10)
    checklist = _normalize_checklist(merged.get("checklist"))
    if not checklist:
        checklist = scaffold["checklist"]
    merged["checklist"] = checklist

    plan["implementation"] = merged
    return plan


def render_implementation_plan_markdown(plan: dict[str, Any], *, mode: str = "") -> str:
    impl = plan.get("implementation")
    if not isinstance(impl, dict):
        return ""
    goal = (plan.get("user_goal") or "").strip()
    lines: list[str] = ["# Implementation Plan", ""]
    if goal:
        lines.extend(["## Goal", goal, ""])
    summary = (impl.get("summary") or "").strip()
    if summary:
        lines.extend(["## Summary", summary, ""])

    def _bullets(title: str, items: Any) -> None:
        vals = _as_str_list(items, limit=20)
        if not vals:
            return
        lines.append(f"## {title}")
        lines.extend(f"- {v}" for v in vals)
        lines.append("")

    _bullets("Acceptance criteria", impl.get("acceptance"))
    _bullets("Files to create", impl.get("files_create"))
    _bullets("Files to modify", impl.get("files_modify"))
    testing = (impl.get("testing_strategy") or "").strip()
    if testing:
        lines.extend(["## Testing strategy", testing, ""])
    _bullets("Sections", impl.get("sections"))
    deliverable = (impl.get("deliverable_path") or "").strip()
    if deliverable:
        lines.extend(["## Deliverable", f"`{deliverable}`", ""])
    _bullets("Research questions", impl.get("research_questions"))
    source = (impl.get("source_strategy") or "").strip()
    if source:
        lines.extend(["## Source strategy", source, ""])
    _bullets("Modules outline", impl.get("modules_outline"))
    _bullets("Persona axes", impl.get("persona_axes"))
    _bullets("Out of scope", impl.get("out_of_scope"))
    _bullets("Risks", impl.get("risks") or plan.get("risks"))

    checklist = _normalize_checklist(impl.get("checklist"))
    if checklist:
        lines.append("## Checklist")
        for item in checklist:
            mark = {"done": "x", "skipped": "-", "pending": " "}.get(item["status"], " ")
            lines.append(f"- [{mark}] {item['text']} `({item['id']})`")
        lines.append("")

    mode_n = (mode or "").strip()
    if mode_n:
        lines.append(f"_Mode: {mode_n}_")
    return "\n".join(lines).rstrip() + "\n"


def format_implementation_for_act(
    plan: dict[str, Any],
    *,
    max_chars: int = 2800,
    open_limit: int = 5,
) -> str:
    """Compact living-plan context for step entry / reflect."""
    impl = plan.get("implementation")
    if not isinstance(impl, dict):
        return ""
    parts: list[str] = ["## Living implementation plan (follow this checklist)"]
    summary = (impl.get("summary") or "").strip()
    if summary:
        parts.append(f"Summary: {summary}")
    acceptance = _as_str_list(impl.get("acceptance"), limit=5)
    if acceptance:
        parts.append("Acceptance:")
        parts.extend(f"- {a}" for a in acceptance)
    files = _as_str_list(impl.get("files_create"), limit=6) + _as_str_list(
        impl.get("files_modify"), limit=6
    )
    if files:
        parts.append("Files: " + ", ".join(f"`{f}`" for f in files[:8]))
    sections = _as_str_list(impl.get("sections"), limit=8)
    if sections:
        parts.append("Sections: " + "; ".join(sections))
    open_items = [
        it for it in _normalize_checklist(impl.get("checklist")) if it["status"] == "pending"
    ][:open_limit]
    if open_items:
        parts.append("Next checklist items:")
        for it in open_items:
            parts.append(f"- [ ] {it['text']} ({it['id']})")
    else:
        parts.append("Checklist: all items done or skipped.")
    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…[truncated]"
    return text


def is_code_impl_source_path(file_path: str) -> bool:
    """True for implementation .py files (not tests, docs, or data JSON)."""
    norm = str(file_path or "").replace("\\", "/").lower().strip()
    if not norm or not norm.endswith(".py"):
        return False
    base = norm.rsplit("/", 1)[-1]
    if base.startswith("test_") or base.endswith("_test.py"):
        return False
    if "/tests/" in norm or norm.startswith("tests/"):
        return False
    return True


def is_code_test_path(file_path: str) -> bool:
    norm = str(file_path or "").replace("\\", "/").lower().strip()
    return bool(norm) and "test" in norm and norm.endswith(".py")


def code_work_checklist_complete(checklist: list[Any]) -> bool:
    """True when core code work checklist items are done (docs/sync optional on work)."""
    required = {"setup-1", "tests-1", "impl-1", "test-1"}
    done = {
        str(getattr(item, "id", "") or (item.get("id") if isinstance(item, dict) else ""))
        for item in checklist
        if (
            (getattr(item, "status", None) or (item.get("status") if isinstance(item, dict) else ""))
            == "done"
        )
    }
    return required.issubset(done)


def update_checklist_items(
    plan: dict[str, Any],
    *,
    mode: str = "code",
    item_ids: list[str] | None = None,
    status: str = "done",
    texts_done: list[str] | None = None,
) -> tuple[dict[str, Any], int]:
    """Mark checklist items by id or fuzzy text match. Returns (plan, updated_count)."""
    ensure_implementation_block(plan, mode)
    impl = plan.get("implementation")
    if not isinstance(impl, dict):
        return plan, 0
    checklist = _normalize_checklist(impl.get("checklist"))
    status_n = (status or "done").strip().lower()
    if status_n not in ("pending", "done", "skipped"):
        status_n = "done"
    id_set = {str(x).strip() for x in (item_ids or []) if str(x).strip()}
    text_needles = [str(t).strip().lower() for t in (texts_done or []) if str(t).strip()]
    updated = 0
    for item in checklist:
        hit = False
        if item["id"] in id_set:
            hit = True
        elif text_needles:
            low = item["text"].lower()
            hit = any(n in low or low in n for n in text_needles)
        if hit and item["status"] != status_n:
            item["status"] = status_n
            updated += 1
    impl["checklist"] = checklist
    plan["implementation"] = impl
    return plan, updated


def infer_completed_items(
    capability_id: str,
    result: Any,
    ground_truth: dict[str, Any],
    *,
    mode: str = "code",
) -> list[str]:
    """Heuristic checklist item ids to auto-tick after a capability succeeds."""
    if not getattr(result, "ok", False):
        return []
    cap = (capability_id or "").strip()
    mode_n = (mode or "").strip().lower()
    ticks: list[str] = []
    data = getattr(result, "data", {}) or {}

    if mode_n == "code":
        if cap == "cap.dev.project_setup@v1":
            ticks.append("setup-1")
        elif cap in ("cap.dev.create_file@v1", "cap.dev.edit_apply@v1"):
            fp = str(data.get("file_path") or data.get("path") or "")
            if fp:
                if is_code_test_path(fp):
                    ticks.append("tests-1")
                elif is_code_impl_source_path(fp):
                    ticks.append("impl-1")
        elif cap == "cap.dev.run_tests@v1":
            ticks.append("test-1")
        elif cap == "cap.dev.sync_project@v1":
            ticks.append("sync-1")
        elif cap == "cap.dev.write_docs@v1":
            ticks.append("docs-1")
    elif mode_n == "writing":
        if cap == "cap.writing.init_document@v1":
            ticks.append("outline-1")
        elif cap == "cap.writing.draft_sections@v1":
            ticks.append("draft-1")
        elif cap in ("cap.writing.compile_document@v1", "cap.writing.finalize_deliverable@v1"):
            ticks.append("final-1")
    elif mode_n == "research":
        if cap in (
            "cap.research.gather_web_sources@v1",
            "cap.web.search@v1",
            "cap.research.ingest_offline@v1",
        ):
            ticks.append("src-1")
        elif cap in ("cap.research.append_note@v1", "cap.research.synthesize_notes@v1"):
            ticks.append("note-1")
        elif cap == "cap.research.finalize_deliverable@v1":
            ticks.append("rep-1")
    elif mode_n == "learn_syllabus_build":
        if cap == "cap.learn.ingest_course_materials@v1":
            ticks.append("ingest-1")
        elif cap == "cap.learn.write_syllabus@v1":
            ticks.append("syll-1")
        elif cap == "cap.learn.finalize_course@v1":
            ticks.append("fin-1")
    elif mode_n == "character_build":
        if cap in ("cap.persona.ingest_sources@v1", "cap.persona.gather_lore@v1"):
            ticks.append("lore-1")
        elif cap == "cap.persona.write_initialization@v1":
            ticks.append("init-1")
        elif cap == "cap.persona.finalize@v1":
            ticks.append("fin-1")
    return ticks
