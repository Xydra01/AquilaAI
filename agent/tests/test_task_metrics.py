import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.parser import analyze_task_jsonl


def test_analyze_task_jsonl_tokens_per_s(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_EXPECTED_TOKENS_PER_S", "30")
    logs = tmp_path / "Agent-Logs"
    logs.mkdir(parents=True)
    jsonl = logs / "demo_task_20260101_120000.jsonl"
    lines = [
        {
            "ts": "2026-01-01T12:00:00",
            "event": "session_start",
            "task": "demo_task",
            "mode": "research",
        },
        {
            "ts": "2026-01-01T12:00:02",
            "event": "llm_response",
            "duration_ms": 1000,
            "body": "x" * 120,
        },
        {
            "ts": "2026-01-01T12:00:10",
            "event": "llm_response",
            "duration_ms": 2000,
            "body": "y" * 80,
        },
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")

    out = analyze_task_jsonl(
        jsonl,
        task_name="demo_task",
        mode="research",
        ledger={
            "ledger_status": "in_progress",
            "current_step_index": 1,
            "total_steps": 2,
        },
    )
    assert out["ok"] is True
    assert out["llm_turns"] == 2
    assert out["throughput"]["last_tokens_per_s"] is not None
    assert out["throughput"]["health"] in ("ok", "degraded", "slow", "unknown")
    assert out["progress"]["eta_seconds"] is not None
