"""Recover research deliverable bodies when the model omits top-level final_report."""
from __future__ import annotations

import re

_FINAL_MARKERS = (
    "FINAL SYNTHESIS",
    "COMPREHENSIVE AGENTIC",
    "--- END REPORT ---",
    "## EXECUTIVE SUMMARY",
    "=== COMPREHENSIVE",
)

_NOTE_SPLIT_RE = re.compile(r"--- Note \d+ ---\n", re.MULTILINE)


def _split_scratchpad_notes(compiled: str) -> list[str]:
    if not compiled or "No research notes found" in compiled:
        return []
    text = compiled
    if "=== SCRATCHPAD NOTES FOR" in text:
        text = text.split("===", 1)[-1]
        if "\n" in text:
            text = text.split("\n", 1)[-1]
    parts = _NOTE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _score_note(note: str) -> int:
    score = len(note)
    upper = note.upper()
    for marker in _FINAL_MARKERS:
        if marker in upper:
            score += 50_000
    if note.lstrip().startswith("#"):
        score += 500
    if "## References" in note and len(note) < 800:
        score -= 10_000
    return score


def pick_best_deliverable_body(compiled_notes: str) -> str:
    """Choose the best scratchpad note to use as the report body."""
    notes = _split_scratchpad_notes(compiled_notes)
    if not notes and (compiled_notes or "").strip():
        notes = [compiled_notes.strip()]
    if not notes:
        return ""
    best = max(notes, key=_score_note)
    if _score_note(best) < 400:
        return ""
    return best


def recover_research_body(
    memory,
    task_name: str,
    *,
    instance_id: str | None = None,
    extra_task_names: tuple[str, ...] = (),
) -> str:
    """
    Load scratchpad notes for the active task only and return the best report body.

    Uses the running loop's task id when set; never scans other tasks on the instance.
    ``extra_task_names`` are optional explicit aliases for the same run (not discovered).
    """
    try:
        from agent.core import get_active_task_id

        active = get_active_task_id()
    except ImportError:
        active = None

    resolved = (active or task_name or "").strip()
    if not resolved:
        return ""

    names: list[str] = []
    for candidate in (resolved, *extra_task_names):
        key = (candidate or "").strip()
        if key and key not in names:
            names.append(key)

    best_body = ""
    best_score = -1
    for name in names:
        try:
            compiled = memory.get_scratchpad_notes(name, instance_id=instance_id)
        except TypeError:
            compiled = memory.get_scratchpad_notes(name)
        except Exception:
            continue
        body = pick_best_deliverable_body(compiled)
        if not body:
            continue
        score = _score_note(body)
        if score > best_score:
            best_score = score
            best_body = body
    return best_body
