"""Live task throughput metrics from Agent-Logs JSONL (tokens/s, ETA, slow detection)."""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.core.capability_scorecard import find_latest_jsonl
from .ollama_diagnostics import chars_to_estimated_tokens, estimate_tokens_metrics
from agent.storage import engine_for_base_url, expected_tokens_per_s
from agent.storage import agent_data_path


def throughput_from_llm_turn(
    body: str,
    duration_ms: int | None,
    *,
    thinking: str = "",
    ollama_base_url: str = "",
) -> dict[str, Any]:
    """Compute output tokens/s for JSONL llm_response events."""
    text = (body or "").strip()
    if not text and (thinking or "").strip():
        text = (thinking or "").strip()
    engine = engine_for_base_url(ollama_base_url) if ollama_base_url else None
    out: dict[str, Any] = {
        "ollama_base_url": ollama_base_url or None,
        "ollama_engine": engine,
    }
    if not duration_ms or int(duration_ms) <= 0:
        return out
    dur_s = int(duration_ms) / 1000.0
    est_tokens, tps = estimate_tokens_metrics(text, duration_s=dur_s)
    out["output_tokens_est"] = est_tokens
    out["output_tokens_per_s"] = round(tps, 2) if tps is not None else None
    baseline = expected_tokens_per_s(engine, base_url=ollama_base_url)
    out["baseline_tokens_per_s"] = baseline
    if tps is not None:
        if tps < baseline * 0.5:
            out["throughput_health"] = "slow"
        elif tps < baseline * 0.85:
            out["throughput_health"] = "degraded"
        else:
            out["throughput_health"] = "ok"
    return out


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _slow_ratio_threshold() -> float:
    try:
        return float(os.getenv("AQUILA_SLOW_TPS_RATIO", "0.5").strip() or "0.5")
    except ValueError:
        return 0.5


def _read_ledger_progress(mode: str, task_name: str) -> dict[str, Any]:
    plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
    path = agent_data_path(plan_dir, f"{task_name}.json")
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    steps = state.get("steps") or []
    idx = int(state.get("current_step_index") or 0)
    total = len(steps)
    done = sum(1 for s in steps if (s.get("status") or "").lower() in ("done", "completed"))
    return {
        "ledger_path": str(path),
        "ledger_status": state.get("status"),
        "current_step_index": idx,
        "total_steps": total,
        "completed_steps": done,
    }


def analyze_task_jsonl(
    jsonl_path: str | Path,
    *,
    task_name: str = "",
    mode: str = "",
    ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse run JSONL and return throughput + progress metrics."""
    p = Path(jsonl_path)
    slow_ratio = _slow_ratio_threshold()
    out: dict[str, Any] = {
        "ok": p.is_file(),
        "task_name": task_name,
        "mode": mode,
        "jsonl_path": str(p.resolve()) if p.is_file() else None,
    }
    if not p.is_file():
        out["error"] = f"JSONL not found for task {task_name!r}"
        return out

    first_ts: datetime | None = None
    last_ts: datetime | None = None
    tps_samples: list[float] = []
    last_tps: float | None = None
    engines_seen: set[str] = set()
    baseline: float | None = None
    llm_turns = 0
    act_turns = 0
    tool_calls = 0
    last_event = ""

    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = rec.get("event", "")
            ts = _parse_ts(str(rec.get("ts", "")))
            if ts:
                first_ts = first_ts or ts
                last_ts = ts
            last_event = ev

            if ev == "act_turn":
                act_turns += 1
            elif ev == "tool_end":
                tool_calls += 1
            elif ev == "llm_response":
                llm_turns += 1
                eng = rec.get("ollama_engine")
                if eng:
                    engines_seen.add(str(eng))
                if rec.get("baseline_tokens_per_s") is not None:
                    try:
                        baseline = float(rec["baseline_tokens_per_s"])
                    except (TypeError, ValueError):
                        pass
                tps_val = rec.get("output_tokens_per_s")
                if tps_val is not None:
                    try:
                        tps_f = float(tps_val)
                        if tps_f > 0:
                            tps_samples.append(tps_f)
                            last_tps = tps_f
                    except (TypeError, ValueError):
                        pass
                else:
                    dur_ms = rec.get("duration_ms")
                    body = rec.get("body") or rec.get("body_preview") or ""
                    thinking = rec.get("thinking_preview") or ""
                    if dur_ms and int(dur_ms) > 0:
                        _, tps = estimate_tokens_metrics(
                            str(body) or str(thinking),
                            duration_s=int(dur_ms) / 1000.0,
                        )
                        if tps is not None and tps > 0:
                            tps_samples.append(tps)
                            last_tps = tps

    wall_s = None
    if first_ts and last_ts:
        wall_s = max(0.0, (last_ts - first_ts).total_seconds())

    median_tps = statistics.median(tps_samples) if tps_samples else None
    avg_tps = statistics.mean(tps_samples) if tps_samples else None
    if baseline is None:
        engine_hint = next(iter(engines_seen), None)
        baseline = expected_tokens_per_s(engine_hint)

    health = "unknown"
    slow = False
    if last_tps is not None:
        if last_tps >= baseline * 0.85:
            health = "ok"
        elif last_tps >= baseline * slow_ratio:
            health = "degraded"
        else:
            health = "slow"
            slow = True
    elif tps_samples:
        if median_tps and median_tps < baseline * slow_ratio:
            health = "slow"
            slow = True
        else:
            health = "degraded"

    progress = dict(ledger or {})
    eta_s = None
    running = (progress.get("ledger_status") or "").lower() in (
        "in_progress",
        "running",
        "pending",
        "",
    )
    if running and wall_s and progress.get("total_steps"):
        total = int(progress["total_steps"])
        idx = int(progress.get("current_step_index") or 0)
        remaining = max(0, total - idx)
        per_step = wall_s / max(1, idx + 1)
        eta_s = round(remaining * per_step, 1)

    out.update(
        {
            "ollama_engines": sorted(engines_seen),
            "baseline_tokens_per_s": baseline,
            "running": running,
            "wall_time_s": round(wall_s, 2) if wall_s is not None else None,
            "llm_turns": llm_turns,
            "act_turns": act_turns,
            "tool_calls": tool_calls,
            "last_event": last_event,
            "throughput": {
                "samples": len(tps_samples),
                "last_tokens_per_s": round(last_tps, 2) if last_tps else None,
                "median_tokens_per_s": round(median_tps, 2) if median_tps else None,
                "avg_tokens_per_s": round(avg_tps, 2) if avg_tps else None,
                "slow_generation": slow,
                "health": health,
            },
            "progress": {
                **progress,
                "eta_seconds": eta_s,
            },
        }
    )
    return out


def get_task_metrics(mode: str, task_name: str) -> dict[str, Any]:
    """Resolve latest JSONL for task and return live metrics."""
    task_name = (task_name or "").strip()
    mode_norm = (mode or "task").strip().lower()
    if not task_name:
        return {"ok": False, "error": "task_name is required"}
    jsonl = find_latest_jsonl(task_name)
    if jsonl is None:
        return {
            "ok": False,
            "task_name": task_name,
            "error": f"No Agent-Logs JSONL found matching {task_name}*",
        }
    ledger = _read_ledger_progress(mode_norm, task_name)
    return analyze_task_jsonl(jsonl, task_name=task_name, mode=mode_norm, ledger=ledger)
