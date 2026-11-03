"""Shared helpers for writing capabilities."""
from __future__ import annotations

import re

from agent.capabilities.base import CapabilityContext, CapabilityResult


def slug_filename(text: str) -> str:
    raw = (text or "document").strip()
    cleaned = re.sub(r"[^\w\s-]", "", raw, flags=re.UNICODE)
    cleaned = re.sub(r"[-\s]+", "-", cleaned).strip("-").lower()
    return (cleaned[:80] or "document")


_IMPERATIVE_TITLE_RE = re.compile(
    r"^(?:please\s+)?(?:write|draft|create|compose|summarize|revise|edit)\s+"
    r"(?:me\s+|out\s+)?(?:a\s+|an\s+|the\s+)?",
    re.IGNORECASE,
)


def title_from_context(ctx: CapabilityContext, explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()[:200]
    req = (ctx.user_request or "").strip()
    if req:
        first = next((ln.strip() for ln in req.splitlines() if ln.strip()), req)
        # Prefer a document title over the raw imperative prompt.
        cleaned = _IMPERATIVE_TITLE_RE.sub("", first).strip(" .:;-")
        cleaned = cleaned[:1].upper() + cleaned[1:] if cleaned else first
        return (cleaned or first)[:200]
    return "Untitled Document"


def from_tool_text(result: str) -> CapabilityResult:
    text = str(result or "")
    if text.startswith("✅"):
        return CapabilityResult.success(text, tool_result=text)
    return CapabilityResult.failure("write_failed", text)
