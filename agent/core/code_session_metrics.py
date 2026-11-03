"""Metrics for simple code chat sessions."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.storage import agent_data_path


@dataclass
class CodeSessionMetrics:
    turns: int = 0
    wall_s: float = 0.0
    parse_failures: int = 0
    capability_errors: int = 0
    heal_invocations: int = 0
    repeat_blocks: int = 0
    model_id: str = ""
    engine: str = ""
    synced: bool = False
    completed: bool = False
    task_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _session_log_enabled() -> bool:
    return os.getenv("AQUILA_CODE_SESSION_LOG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def append_code_session_log(
    metrics: CodeSessionMetrics,
    *,
    summary: str = "",
) -> None:
    """Append one JSONL record for a completed code session."""
    if not _session_log_enabled():
        return
    logs = agent_data_path("Agent-Logs")
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "code-sessions.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_name": metrics.task_name,
        "model_id": metrics.model_id,
        "engine": metrics.engine,
        "summary": (summary or "")[:500],
        "metrics": metrics.to_dict(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
