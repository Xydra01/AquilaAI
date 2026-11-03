"""Draft scope satisfaction checks for writing mode."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.functions.writing_brief import WritingBrief
from agent.tool_library.writing_tools import ACTIVE_DRAFT_FILE


def load_draft_state(path: Path | None = None) -> dict[str, Any] | None:
    state_path = path or ACTIVE_DRAFT_FILE
    if not state_path.is_file():
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def draft_metrics(state: dict[str, Any] | None) -> dict[str, int]:
    if not state:
        return {"sections": 0, "words": 0, "paragraphs": 0}
    sections = state.get("sections") or []
    section_count = len(sections)
    words = 0
    paragraphs = 0
    for sec in sections:
        content = str(sec.get("content") or "")
        words += len(content.split())
        paragraphs += max(1, len([p for p in content.split("\n\n") if p.strip()])) if content.strip() else 0
    if section_count == 0:
        return {"sections": 0, "words": 0, "paragraphs": 0}
    return {"sections": section_count, "words": words, "paragraphs": paragraphs}


def draft_scope_satisfied(
    brief: WritingBrief | dict[str, Any] | None,
    draft_state: dict[str, Any] | None = None,
    *,
    draft_sections_calls: int = 0,
) -> bool:
    """Return True when the active draft meets brief length/section targets."""
    if brief is None:
        return draft_sections_calls >= 1

    if isinstance(brief, dict):
        brief = WritingBrief.from_plan_dict(brief)
    if brief is None:
        return draft_sections_calls >= 1

    if brief.advance_when == "single_draft":
        return draft_sections_calls >= 1

    if brief.advance_when == "manual":
        return False

    state = draft_state if draft_state is not None else load_draft_state()
    metrics = draft_metrics(state)

    if brief.length_mode == "flexible":
        if brief.target_sections and metrics["sections"] >= brief.target_sections:
            return True
        if brief.target_words and metrics["words"] >= brief.target_words:
            return True
        return draft_sections_calls >= 1 and metrics["sections"] >= 1

    if brief.length_mode == "words" and brief.target_words:
        return metrics["words"] >= brief.target_words

    if brief.length_mode == "paragraphs" and brief.target_paragraphs:
        return metrics["paragraphs"] >= brief.target_paragraphs

    if brief.length_mode == "sections" and brief.target_sections:
        return metrics["sections"] >= brief.target_sections

    if brief.target_words and metrics["words"] >= brief.target_words:
        return True
    if brief.target_sections and metrics["sections"] >= brief.target_sections:
        return True

    return False
