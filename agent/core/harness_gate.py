"""Harness gate: preflight checks and required scenario runs."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from agent.core.capability_harness import (
    GATE_SCENARIO_IDS,
    configure_engine,
    run_and_evaluate,
)
from agent.policies.model_tiers import check_code_model, code_model_tier, get_active_model_id
from agent.storage import agent_data_path, ensure_repo_cwd

DEFAULT_SCENARIOS = GATE_SCENARIO_IDS


def run_gate(
    *,
    engine: str = "stock",
    allow_degraded: bool = False,
    runs: int = 1,
    scenario_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run harness gate scenarios; return summary dict."""
    ensure_repo_cwd()
    scenarios = scenario_ids or DEFAULT_SCENARIOS
    runs = max(1, int(runs))

    ok_eng, eng_msg = configure_engine(engine)
    if not ok_eng:
        return {
            "ok": False,
            "error": eng_msg,
            "engine": engine,
        }

    model_id = get_active_model_id()
    tier = code_model_tier(model_id)
    model_check = check_code_model(surface="harness", strict=not allow_degraded, model_id=model_id)
    if not model_check.ok:
        return {
            "ok": False,
            "error": model_check.message,
            "model_id": model_id,
            "model_tier": tier,
            "engine": engine,
        }

    summary: dict[str, Any] = {
        "ok": True,
        "engine": engine,
        "model_id": model_id,
        "model_tier": tier,
        "runs_per_scenario": runs,
        "scenarios": {},
        "failures": [],
    }
    if model_check.warn and model_check.message:
        summary["warnings"] = [model_check.message]

    for sid in scenarios:
        scenario_runs: list[dict[str, Any]] = []
        all_passed = True
        for run_idx in range(runs):
            passed, rep = run_and_evaluate(sid, engine=engine, allow_degraded=allow_degraded)
            run_record = {
                "run": run_idx + 1,
                "passed": passed,
                "failures": rep.get("failures") or [],
                "task_name": rep.get("task_name"),
                "wall_time_s": rep.get("wall_time_s") or (rep.get("code_session_metrics") or {}).get("wall_s"),
                "turns": (rep.get("code_session_metrics") or {}).get("turns"),
                "parse_failures": (rep.get("code_session_metrics") or {}).get("parse_failures"),
            }
            scenario_runs.append(run_record)
            if not passed:
                all_passed = False
                summary["failures"].extend(
                    [f"{sid} run {run_idx + 1}: {f}" for f in (rep.get("failures") or ["failed"])]
                )
        pass_count = sum(1 for r in scenario_runs if r.get("passed"))
        summary["scenarios"][sid] = {
            "runs": scenario_runs,
            "pass_rate": pass_count / runs if runs else 0.0,
            "passed": all_passed,
        }
        if not all_passed:
            summary["ok"] = False

    return summary


def capture_baseline(
    *,
    scenario_ids: tuple[str, ...] | None = None,
    runs: int = 3,
    engine: str = "stock",
    allow_degraded: bool = False,
) -> dict[str, Any]:
    """Run scenarios multiple times and return baseline summary."""
    result = run_gate(
        engine=engine,
        allow_degraded=allow_degraded,
        runs=runs,
        scenario_ids=scenario_ids,
    )
    result["captured_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


def write_baseline(path: str | None = None, **kwargs: Any) -> str:
    """Capture baseline and write JSON file; return path."""
    data = capture_baseline(**kwargs)
    out = path or str(agent_data_path("Agent-Logs", "baseline-aug-2026.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    data["baseline_path"] = out
    return out


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(argv or sys.argv[1:])
    engine = "stock"
    allow_degraded = False
    runs = 1
    write_baseline_file = False
    i = 0
    while i < len(argv):
        if argv[i] == "--engine" and i + 1 < len(argv):
            engine = argv[i + 1].strip().lower()
            i += 2
        elif argv[i] == "--allow-degraded":
            allow_degraded = True
            i += 1
        elif argv[i] == "--runs" and i + 1 < len(argv):
            runs = int(argv[i + 1])
            i += 2
        elif argv[i] == "--baseline":
            write_baseline_file = True
            i += 1
        elif argv[i] in ("-h", "--help"):
            print(
                "Usage: python -m agent.core.harness_gate "
                "[--engine stock|tq] [--allow-degraded] [--runs N] [--baseline]"
            )
            return 0
        else:
            i += 1

    if write_baseline_file:
        if runs == 1:
            runs = 3
        data = capture_baseline(engine=engine, allow_degraded=allow_degraded, runs=runs)
        path = str(agent_data_path("Agent-Logs", "baseline-aug-2026.json"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        data["baseline_path"] = path
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0 if data.get("ok") else 1

    summary = run_gate(engine=engine, allow_degraded=allow_degraded, runs=runs)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
