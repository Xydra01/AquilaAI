"""Writing brief schema — scope, tone, and length settings for writing mode."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WritingScope = Literal["quick_edit", "short_form", "standard", "from_sources"]
WritingTone = Literal["neutral", "formal", "conversational", "technical", "custom"]
LengthMode = Literal["words", "paragraphs", "sections", "flexible"]
AdvanceWhen = Literal["scope_met", "single_draft", "manual"]

SCOPE_PRESETS: dict[WritingScope, dict[str, Any]] = {
    "quick_edit": {
        "label": "Quick edit / paragraph",
        "advance_when": "single_draft",
        "length_mode": "flexible",
        "target_words": None,
        "target_paragraphs": 1,
        "target_sections": 1,
    },
    "short_form": {
        "label": "Short note",
        "advance_when": "single_draft",
        "length_mode": "words",
        "target_words": 400,
        "target_paragraphs": None,
        "target_sections": 1,
    },
    "standard": {
        "label": "Document",
        "advance_when": "scope_met",
        "length_mode": "sections",
        "target_words": 1500,
        "target_paragraphs": None,
        "target_sections": 4,
    },
    "from_sources": {
        "label": "Source summary",
        "advance_when": "scope_met",
        "length_mode": "sections",
        "target_words": 2000,
        "target_paragraphs": None,
        "target_sections": 4,
    },
}


class WritingBrief(BaseModel):
    scope: WritingScope = "standard"
    tone: WritingTone = "neutral"
    tone_custom: str = ""
    length_mode: LengthMode = "sections"
    target_words: int | None = None
    target_paragraphs: int | None = None
    target_sections: int | None = 4
    advance_when: AdvanceWhen = "scope_met"
    target_document: str | None = None
    has_attachments: bool = False

    @classmethod
    def from_scope_preset(
        cls,
        scope: WritingScope,
        *,
        tone: WritingTone = "neutral",
        tone_custom: str = "",
        length_mode: LengthMode | None = None,
        target_words: int | None = None,
        target_paragraphs: int | None = None,
        target_sections: int | None = None,
        advance_when: AdvanceWhen | None = None,
        target_document: str | None = None,
        has_attachments: bool = False,
    ) -> WritingBrief:
        preset = SCOPE_PRESETS.get(scope, SCOPE_PRESETS["standard"])
        return cls(
            scope=scope,
            tone=tone,
            tone_custom=tone_custom,
            length_mode=length_mode or preset["length_mode"],
            target_words=target_words if target_words is not None else preset.get("target_words"),
            target_paragraphs=(
                target_paragraphs
                if target_paragraphs is not None
                else preset.get("target_paragraphs")
            ),
            target_sections=(
                target_sections
                if target_sections is not None
                else preset.get("target_sections")
            ),
            advance_when=advance_when or preset["advance_when"],
            target_document=target_document,
            has_attachments=has_attachments,
        )

    def tone_label(self) -> str:
        if self.tone == "custom" and self.tone_custom.strip():
            return self.tone_custom.strip()
        return self.tone.replace("_", " ")

    def length_summary(self) -> str:
        if self.length_mode == "words" and self.target_words:
            return f"~{self.target_words} words"
        if self.length_mode == "paragraphs" and self.target_paragraphs:
            return f"~{self.target_paragraphs} paragraph(s)"
        if self.length_mode == "sections" and self.target_sections:
            return f"~{self.target_sections} section(s)"
        return "flexible length"

    def milestone_summary(self) -> str:
        parts = [self.tone_label(), self.length_summary()]
        if self.scope == "quick_edit":
            parts.append("single targeted revision")
        elif self.advance_when == "scope_met":
            parts.append("complete all planned sections before advancing")
        return "; ".join(parts)

    def planner_block(self) -> str:
        lines = [
            f"scope={self.scope}",
            f"tone={self.tone_label()}",
            f"length={self.length_summary()}",
            f"advance_when={self.advance_when}",
        ]
        if self.target_document:
            lines.append(f"target_document={self.target_document}")
        if self.has_attachments:
            lines.append("has_attachments=true")
        return "\n".join(lines)

    def to_plan_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_plan_dict(cls, data: dict[str, Any] | None) -> WritingBrief | None:
        if not data or not isinstance(data, dict):
            return None
        try:
            return cls.model_validate(data)
        except Exception:
            return None
