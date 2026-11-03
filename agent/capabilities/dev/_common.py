"""Shared helpers for code/dev capabilities."""
from __future__ import annotations

from agent.capabilities.base import CapabilityResult


def from_tool_text(result: str, *, ok_summary: str = "") -> CapabilityResult:
    text = str(result or "")
    if text.startswith("✅") or text.startswith("⚠️"):
        return CapabilityResult.success(ok_summary or text, tool_result=text)
    if text.startswith("❌"):
        return CapabilityResult.failure("tool_error", text)
    # Some tools return plain success without emoji
    low = text.lower()
    if "error" in low[:80] and not text.strip().startswith("OUTLINE"):
        return CapabilityResult.failure("tool_error", text)
    return CapabilityResult.success(ok_summary or text[:240], tool_result=text)
