"""Per-run URL visit tracking with hard duplicate blocking."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from web_content_quality import PageQuality
from web_enrichment import normalize_url

VisitVia = Literal["auto_scrape", "read_webpage"]


@dataclass
class UrlVisitRecord:
    url: str
    normalized: str
    attempts: int = 0
    via: VisitVia = "read_webpage"
    quality: PageQuality = "full"
    char_count: int = 0
    content_hash: str = ""
    step_index: int | None = None


@dataclass
class UrlVisitRegistry:
    """Tracks URLs fetched during one task run."""

    _records: dict[str, UrlVisitRecord] = field(default_factory=dict)
    _read_webpage_step_counts: dict[str, int] = field(default_factory=dict)
    _current_step_index: int = 0

    def set_step_index(self, step_index: int) -> None:
        self._current_step_index = step_index

    def seen_normalized(self) -> set[str]:
        return set(self._records.keys())

    def get(self, url: str) -> UrlVisitRecord | None:
        return self._records.get(normalize_url(url))

    def already_scraped(self, url: str) -> bool:
        return normalize_url(url) in self._records

    def check_read_webpage(self, url: str) -> str | None:
        """
        Return OS block message if read_webpage must not run, else None.
        """
        norm = normalize_url(url)
        if not norm:
            return "❌ OS BLOCK: Invalid URL."
        rec = self._records.get(norm)
        if not rec:
            return None
        if rec.quality == "paywall":
            return (
                f"❌ OS BLOCK: {url} was already fetched and classified as paywall. "
                "Use search snippets or an open-access URL."
            )
        step_key = f"{self._current_step_index}:{norm}"
        step_reads = self._read_webpage_step_counts.get(step_key, 0)
        if rec.via == "read_webpage" or step_reads >= 1:
            return (
                f"❌ OS BLOCK: {url} was already fetched this run "
                f"(quality={rec.quality}, attempts={rec.attempts}). "
                "Use a different URL or synthesize from prior tool output."
            )
        if rec.attempts >= 2:
            return (
                f"❌ OS BLOCK: {url} reached visit limit ({rec.attempts} attempts). "
                "Try a different source."
            )
        return None

    def register_visit(
        self,
        url: str,
        *,
        via: VisitVia,
        quality: PageQuality,
        body: str,
        step_index: int | None = None,
    ) -> UrlVisitRecord:
        norm = normalize_url(url)
        step_index = step_index if step_index is not None else self._current_step_index
        content_hash = hashlib.sha256((body or "").encode("utf-8", errors="replace")).hexdigest()[:8]
        char_count = len(body or "")

        rec = self._records.get(norm)
        if rec:
            rec.attempts += 1
            rec.via = via
            rec.quality = quality
            rec.char_count = char_count
            rec.content_hash = content_hash
            rec.step_index = step_index
        else:
            rec = UrlVisitRecord(
                url=url.strip(),
                normalized=norm,
                attempts=1,
                via=via,
                quality=quality,
                char_count=char_count,
                content_hash=content_hash,
                step_index=step_index,
            )
            self._records[norm] = rec

        if via == "read_webpage":
            step_key = f"{step_index}:{norm}"
            self._read_webpage_step_counts[step_key] = (
                self._read_webpage_step_counts.get(step_key, 0) + 1
            )
        return rec

    def check_web_search_query(self, query: str) -> str | None:
        """Block identical web_search query 3+ times in a row (signature list)."""
        return None  # handled via tool signatures in loop_engine

    @staticmethod
    def tool_signature(tool_name: str, arguments: dict) -> str:
        return json.dumps({"name": tool_name, "arguments": arguments}, sort_keys=True)

    def duplicate_tool_block(self, signatures: list[str]) -> str | None:
        """Hard block on 3rd identical tool call (upgrade from warn-only)."""
        if len(signatures) < 3:
            return None
        if signatures[-1] == signatures[-2] == signatures[-3]:
            return (
                "❌ OS BLOCK: Same tool call repeated three times. "
                "Use a different tool, URL, or query — or mark_objective_complete / finish_task."
            )
        return None

    def duplicate_tool_warning(self, signatures: list[str]) -> str | None:
        if len(signatures) < 2:
            return None
        if signatures[-1] == signatures[-2]:
            return (
                "⚠️ OS WARNING: You repeated the same tool call twice. "
                "Try a different approach or mark_objective_complete."
            )
        return None
