"""Recovery coaching messages when the loop OS blocks duplicate tools or URLs."""
from __future__ import annotations

import json
import re
from typing import Any

from agent.research import UrlVisitRegistry
from agent.research import normalize_url

_URL_RE = re.compile(r"https?://[^\s\)\]>\"']+", re.I)


def _extract_urls_from_search(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in _URL_RE.findall(text or ""):
        norm = normalize_url(raw)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(raw.strip())
    return out


def _unused_urls(last_search_text: str, visited: set[str], limit: int = 3) -> list[str]:
    candidates = _extract_urls_from_search(last_search_text)
    unused: list[str] = []
    for url in candidates:
        if normalize_url(url) not in visited:
            unused.append(url)
        if len(unused) >= limit:
            break
    return unused


class LoopCoach:
    """Mode-aware recovery hints appended to OS block / warning messages."""

    def __init__(
        self,
        *,
        mode: str = "",
        step_kind: str = "",
        persona_research_lore: bool = False,
        learn_syllabus_web: bool = False,
        offline_research: bool = False,
        capability_research: bool = False,
    ):
        self.mode = mode or "task"
        self.step_kind = step_kind or ""
        self.persona_research_lore = persona_research_lore
        self.learn_syllabus_web = learn_syllabus_web
        self.offline_research = offline_research
        self.capability_research = capability_research
        self._last_web_search_text: str = ""

    def record_web_search_result(self, result_text: str) -> None:
        if result_text:
            self._last_web_search_text = result_text

    def enhance_url_block(
        self,
        block_msg: str,
        url: str,
        url_registry: UrlVisitRegistry,
    ) -> str:
        if not block_msg or "OS BLOCK" not in block_msg:
            return block_msg
        visited = url_registry.seen_normalized()
        unused = _unused_urls(self._last_web_search_text, visited)
        parts = [block_msg.rstrip()]
        if unused:
            parts.append("\n\n💡 COACH: Try an unused URL from your last search:")
            for u in unused:
                parts.append(f"  • {u}")
        else:
            parts.append(
                "\n\n💡 COACH: No fresh URLs in the last search — run web_search with a "
                "different query, or distill facts with save_research_note from snippets "
                "you already have."
            )
        if self.mode == "character_build":
            if self.step_kind == "search":
                parts.append(
                    "\nIf scratchpad already has enough lore, call mark_objective_complete "
                    "on the search step — synthesize is next."
                )
            elif self.step_kind == "read":
                parts.append(
                    "\nOn read/ingest, use save_research_note with user text + prior tool "
                    "output, then mark_objective_complete (do not re-read the same URL)."
                )
        elif self.mode == "research" and self.step_kind in ("search", "read"):
            parts.append(
                "\nOr save_research_note from existing snippets and mark_objective_complete."
            )
        if "truncat" in block_msg.lower() or "fandom" in url.lower():
            parts.append(
                "\nWiki tip: Fandom pages often truncate nav chrome — try Reddit threads "
                "from search or a different wiki section."
            )
        return "\n".join(parts)

    def enhance_duplicate_tool_warning(self, warning_msg: str) -> str:
        if not warning_msg:
            return warning_msg
        hint = self._duplicate_hint(soft=True)
        return f"{warning_msg.rstrip()}\n\n{hint}"

    def enhance_duplicate_tool_block(self, block_msg: str) -> str:
        if not block_msg:
            return block_msg
        hint = self._duplicate_hint(soft=False)
        return f"{block_msg.rstrip()}\n\n{hint}"

    def _duplicate_hint(self, *, soft: bool) -> str:
        prefix = "💡 COACH" if soft else "💡 COACH (required)"
        try:
            from .loop_settings import dynamic_loop_enabled

            if dynamic_loop_enabled() and self.mode in (
                "code",
                "research",
                "writing",
                "task",
                "autonomous",
            ):
                return (
                    f"{prefix}: You already have enough evidence — try a different tool, "
                    "synthesize notes, run tests, or mark_objective_complete / finish_task "
                    "when milestones are met."
                )
        except ImportError:
            pass
        if self.mode == "character_build":
            if self.step_kind == "search":
                return (
                    f"{prefix}: Change URL/query, save_research_note with distilled bullets, "
                    "or mark_objective_complete if lore is enough."
                )
            if self.step_kind == "read":
                return (
                    f"{prefix}: save_research_note once from user text + prior reads, then "
                    "mark_objective_complete — do not repeat read_webpage."
                )
            if self.step_kind == "synthesize":
                return (
                    f"{prefix}: read_all_research_notes once, then write_persona_file for "
                    "initialization.md."
                )
        if self.mode == "learn_syllabus_build":
            if self.step_kind in ("search", "read"):
                return (
                    f"{prefix}: save_research_note or mark_objective_complete; "
                    "write_syllabus_file is only on synthesize."
                )
        if self.mode == "research":
            return (
                f"{prefix}: Use a different source, save_research_note, or "
                "mark_objective_complete / finish_task on finalize."
            )
        if self.mode == "code":
            return (
                f"{prefix}: Switch tools (grep vs read_file), read a different path, "
                "or mark_objective_complete when the step objective is satisfied."
            )
        return (
            f"{prefix}: Use a different tool/arguments, or mark_objective_complete "
            "if this step's work is done."
        )

    def repetition_break_hint(
        self,
        pending_milestones: list[str],
        valid_tools: frozenset[str],
    ) -> str:
        """Coaching hint injected when 3+ identical model outputs are detected."""
        from agent.core.loop_objectives import milestone_hints_for_mode

        parts = [
            "❌ OS BLOCK (repetition detected): You have repeated the same "
            "output 3 times. You MUST use a different approach.",
            "",
            f"💡 COACH: Pending milestones: {', '.join(pending_milestones)}.",
        ]
        tool_hints = milestone_hints_for_mode(
            self.mode,
            offline=self.offline_research,
            capability=self.capability_research,
        )
        for ms in pending_milestones:
            if ms in tool_hints:
                suggested = [t for t in tool_hints[ms] if t in valid_tools]
                if suggested:
                    parts.append(
                        f"  → To satisfy '{ms}': use {' or '.join(suggested)}"
                    )
        label = "Valid capabilities" if self.capability_research else "Valid tools"
        parts.append(f"\n{label}: {', '.join(sorted(valid_tools))}")
        return "\n".join(parts)

    @staticmethod
    def github_blob_404_hint() -> str:
        return (
            "\n\n💡 COACH: GitHub /blob/ URLs often 404 in scrapers. Use the repo root URL "
            "(https://github.com/org/repo) or raw.githubusercontent.com for a single file."
        )

    @staticmethod
    def try_merge_scratchpad(gathered: str, existing_notes: str) -> str | None:
        """Append only new bullet lines when a full note would be blocked as repetitive."""
        new_lines = [
            ln.strip()
            for ln in (gathered or "").splitlines()
            if ln.strip().startswith(("-", "*"))
        ]
        if not new_lines:
            return None
        existing = set((existing_notes or "").splitlines())
        fresh = [ln for ln in new_lines if ln not in existing]
        if not fresh:
            return None
        merged = (existing_notes or "").rstrip()
        if merged:
            merged += "\n"
        merged += "\n".join(fresh)
        return merged

    def scratchpad_quality_block(self, gathered_data: str) -> str | None:
        text = (gathered_data or "").strip()
        if text.startswith("No research notes found"):
            return (
                "❌ OS BLOCK: gathered_data must be your own findings, not the empty "
                "scratchpad placeholder. Run web_search / read_webpage first."
            )
        min_chars = 40
        if text and len(text) < min_chars:
            return (
                f"❌ OS BLOCK: Research note too short ({len(text)} chars). "
                f"Add at least {min_chars} characters of distilled facts."
            )
        if not text:
            return "❌ OS BLOCK: save_research_note requires non-empty gathered_data."
        words = re.findall(r"\b\w+\b", text.lower())
        bullet_lines = [
            ln for ln in text.splitlines() if re.match(r"^\s*[-*]\s+", ln)
        ]
        is_mostly_bullets = len(bullet_lines) >= 3 and len(bullet_lines) >= max(
            1, len(text.splitlines()) // 2
        )
        if len(words) >= 20:
            unique_ratio = len(set(words)) / len(words)
            threshold = 0.28 if is_mostly_bullets else 0.35
            if unique_ratio < threshold:
                return (
                    "❌ OS BLOCK: Note has too little unique vocabulary. Write distinct "
                    "bullet facts instead of repeating the same phrase."
                )
        return None

    def persona_search_complete_hint(self) -> str:
        return (
            "\n✅ OS COACH: Lore saved on search step. Call mark_objective_complete now — "
            "do not re-read the same URL. Read/ingest step is next only if you still "
            "need user attachment text."
        )

    def persona_read_skip_hint(self) -> str:
        return (
            "\n✅ OS COACH: Scratchpad already has lore from search. save_research_note "
            "if needed for user attachments, then mark_objective_complete — skipping "
            "duplicate web reads."
        )

    @staticmethod
    def tool_signature(tool_name: str, arguments: dict[str, Any]) -> str:
        return json.dumps({"name": tool_name, "arguments": arguments}, sort_keys=True)
