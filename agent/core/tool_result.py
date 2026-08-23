"""Stable tool result formatting for loop parsing and logs."""
from __future__ import annotations


def format_tool_result(
    status: str,
    summary: str,
    detail: str = "",
    *,
    artifacts: list[str] | None = None,
) -> str:
    """status: OK | WARN | ERROR"""
    st = (status or "OK").upper()
    head = f"[{st}] {summary.strip()}"
    parts = [head]
    if detail and detail.strip():
        parts.append(detail.strip())
    if artifacts:
        parts.append("Artifacts: " + ", ".join(artifacts[:20]))
    return "\n".join(parts)
