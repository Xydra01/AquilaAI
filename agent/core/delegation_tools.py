"""Autonomous mode delegation meta-tool (handled by LoopEngine)."""
from __future__ import annotations


def delegate_mode(mode: str, objective: str, context: str = "") -> str:
    """Delegate work to a specialized mode loop (research, code, writing).

    This tool is executed by the OS loop engine, not as a normal survival tool.
    """
    return (
        f"delegate_mode queued: mode={mode!r} objective={objective[:120]!r} "
        "(handled by LoopEngine)"
    )
