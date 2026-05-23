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
    Load scratchpad notes for task_name (and optional aliases) and return the best report body.
    If the model saved notes under a different slug on the same instance, scan all
    instance scratchpads and pick the best synthesis note.
    """
    # #region agent log
    try:
        import json as _json
        import time as _time
        from pathlib import Path as _Path

        _log = _Path(__file__).resolve().parents[1] / "debug-5063e5.log"  # repo root
        with open(_log, "a", encoding="utf-8") as _f:
            _f.write(
                _json.dumps(
                    {
                        "sessionId": "5063e5",
                        "hypothesisId": "H3",
                        "location": "research_deliverable.py:recover_research_body",
                        "message": "recover_start",
                        "data": {"task_name": task_name},
                        "timestamp": int(_time.time() * 1000),
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    # #endregion

    candidates: list[str] = []
    names: list[str] = [task_name, *extra_task_names]
    list_fn = getattr(memory, "list_scratchpad_task_names", None)
    if callable(list_fn):
        try:
            names.extend(list_fn(instance_id=instance_id))
        except TypeError:
            names.extend(list_fn())
    seen: set[str] = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            compiled = memory.get_scratchpad_notes(name, instance_id=instance_id)
        except TypeError:
            compiled = memory.get_scratchpad_notes(name)
        except Exception:
            continue
        body = pick_best_deliverable_body(compiled)
        if body:
            candidates.append(body)
    if not candidates:
        return ""
    best = max(candidates, key=_score_note)
    # #region agent log
    try:
        import json as _json
        import time as _time
        from pathlib import Path as _Path

        _log = _Path(__file__).resolve().parents[1] / "debug-5063e5.log"  # repo root
        with open(_log, "a", encoding="utf-8") as _f:
            _f.write(
                _json.dumps(
                    {
                        "sessionId": "5063e5",
                        "hypothesisId": "H3",
                        "location": "research_deliverable.py:recover_research_body",
                        "message": "recover_ok",
                        "data": {"task_name": task_name, "body_len": len(best)},
                        "timestamp": int(_time.time() * 1000),
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    # #endregion
    return best
