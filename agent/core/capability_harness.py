"""Recursive capability harness: scenarios, run reports, evaluation gates."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .capability_scorecard import find_latest_jsonl, score_jsonl_for_scenario
from .generation_lock import _clear_stale_lock, _lock_path, _pid_alive, read_lock_info, release
from agent.parser import get_task_metrics
from agent.storage import agent_data_path, ensure_repo_cwd

HARNESS_SCENARIOS: dict[str, dict[str, Any]] = {
    "code_smoke_file": {
        "description": "Create harness_smoke.py in active code project",
        "mode": "code",
        "objective": (
            "Call init_code_project('harness-smoke') first. In that sandbox create "
            "harness_smoke.py with print('HARNESS_OK'). Call sync_project_to_disk, "
            "run python harness_smoke.py once, then finish."
        ),
        "context": (
            "Use only the harness-smoke code project under Agent-Code/. "
            "No repo-wide exploration. Max 6 tool rounds."
        ),
        "file_paths": [],
        "prefer_local": True,
        "instance_id": "preon-agent-1",
        "rubric_key": "code_smoke_file",
        "max_wall_s": 600,
        "force_micro_plan": True,
        "code_micro_single_step": True,
        "acceptance": {
            "check_file_glob": "**/harness_smoke.py",
            "file_contains": "HARNESS_OK",
        },
    },
    "code_local_read": {
        "description": "Summarize generation_lock.py via local reads",
        "mode": "code",
        "objective": (
            "Summarize how generation_lock.py serializes GPU use across GUI, MCP, and remote. "
            "Write a short markdown deliverable."
        ),
        "context": "Use read_file and grep only; no web_search.",
        "file_paths": ["agent/core/generation_lock.py", "agent/core/main.py"],
        "prefer_local": True,
        "instance_id": "preon-agent-1",
        "rubric_key": "code_local_read",
        "max_wall_s": 600,
        "force_micro_plan": True,
        "acceptance": {"min_deliverable_chars": 100},
    },
    "research_local_lock": {
        "description": "Local research on generation lock (no web)",
        "mode": "research",
        "objective": (
            "Produce a research note explaining how generation_lock.py prevents "
            "concurrent Ollama generations across processes."
        ),
        "context": (
            "Attached files cover the implementation. Use offline ingest / synthesize "
            "capabilities only — no web capabilities."
        ),
        "file_paths": ["agent/core/generation_lock.py", "agent/core/mcp_host.py"],
        "prefer_local": True,
        "instance_id": "ai-researcher",
        "rubric_key": "research_local_lock",
        "max_wall_s": 900,
        "acceptance": {"min_deliverable_chars": 400},
    },
    "writing_short": {
        "description": "Short writing draft (local topic)",
        "mode": "writing",
        "objective": (
            "Write a 2-paragraph markdown draft titled 'Aquila Generation Lock' "
            "explaining why only one generation runs at a time."
        ),
        "context": "No web research required.",
        "file_paths": ["agent/core/generation_lock.py"],
        "prefer_local": True,
        "instance_id": "default",
        "rubric_key": "writing_short",
        "max_wall_s": 600,
        "acceptance": {"min_deliverable_chars": 300},
    },
    "autonomous_trivial_harness": {
        "description": "Short autonomous-style task (local docs only)",
        "mode": "task",
        "objective": "List three bullet points describing what generation.lock stores.",
        "context": "Read agent/core/generation_lock.py only. No web_search.",
        "file_paths": ["agent/core/generation_lock.py"],
        "prefer_local": True,
        "instance_id": "default",
        "rubric_key": "autonomous_trivial",
        "max_wall_s": 600,
        "force_micro_plan": True,
        "acceptance": {"min_deliverable_chars": 80},
    },
    "research_web_chronology_mini": {
        "description": "Two-conflict chronological web research (Iran–Israel + Israel–Lebanon)",
        "mode": "research",
        "objective": (
            "Chronological report covering both the Iran–Israel war and the Israel–Lebanon "
            "war: ordered dated events for each conflict, then a short comparative timeline. "
            "Use cap.research.gather_web_sources@v1 for each conflict, read primary sources, "
            "and append notes via research capabilities."
        ),
        "context": (
            "Require at least two gather-web-sources capability calls and one page read before "
            "finalize. Sections must mention both conflicts. Put the full report in "
            "final_report and call cap.research.finalize_deliverable@v1. No repo tools."
        ),
        "file_paths": [],
        "prefer_local": False,
        "instance_id": "ai-researcher",
        "rubric_key": "research_web_chronology_mini",
        "max_wall_s": 900,
        "force_micro_plan": True,
        "acceptance": {"min_deliverable_chars": 800},
    },
    "task_lock_check": {
        "description": "Autonomous task documenting lock behavior",
        "mode": "task",
        "objective": (
            "Document Aquila cross-process generation lock: file path, acquire/release, "
            "and what MCP host returns when busy."
        ),
        "context": "Read agent/core/generation_lock.py and agent/core/mcp_host.py locally.",
        "file_paths": ["agent/core/generation_lock.py", "agent/core/mcp_host.py"],
        "prefer_local": True,
        "instance_id": "default",
        "rubric_key": "task_lock_check",
        "max_wall_s": 900,
        "acceptance": {"min_deliverable_chars": 200},
    },
}


def clear_harness_stale_state() -> dict[str, Any]:
    """Clear dead-process generation locks before a harness run."""
    _clear_stale_lock()
    info = read_lock_info()
    cleared = False
    if info is not None and info.pid != os.getpid() and not _pid_alive(info.pid):
        try:
            _lock_path().unlink(missing_ok=True)
            cleared = True
        except OSError:
            pass
    return {
        "ok": True,
        "lock_cleared": cleared,
        "lock": read_lock_info().to_dict() if read_lock_info() else None,
    }


def release_generation_lock_force() -> dict[str, Any]:
    """Release lock if held by current process, else clear stale."""
    clear_harness_stale_state()
    info = read_lock_info()
    if info and info.pid == os.getpid():
        release()
        return {"ok": True, "released": True, "was_owner": True}
    return {"ok": True, "released": False, "lock": info.to_dict() if info else None}


def list_scenarios(*, mode: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for sid, spec in HARNESS_SCENARIOS.items():
        if mode and (spec.get("mode") or "").lower() != mode.strip().lower():
            continue
        rows.append(
            {
                "id": sid,
                "description": spec.get("description", ""),
                "mode": spec.get("mode"),
                "rubric_key": spec.get("rubric_key"),
                "max_wall_s": spec.get("max_wall_s"),
                "instance_id": spec.get("instance_id"),
            }
        )
    return rows


def get_scenario(scenario_id: str) -> dict[str, Any] | None:
    return HARNESS_SCENARIOS.get((scenario_id or "").strip())


def _runs_dir() -> Path:
    d = agent_data_path("Agent-Logs") / "capability-runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _code_project_harness_file(needle: str) -> Path | None:
    """Find harness_smoke.py in active code buffer or on-disk code project root."""
    state_path = agent_data_path("Agent-Code", "active_code_state.json")
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    code_root = (state.get("root") or "").strip()
    for entry in state.get("files") or []:
        rel = str(entry.get("path") or "")
        if "harness_smoke" not in rel.lower():
            continue
        content = str(entry.get("content") or "")
        if needle in content:
            if code_root:
                on_disk = Path(code_root) / rel
                if on_disk.is_file():
                    return on_disk
            return Path(rel)
    if code_root:
        candidate = Path(code_root) / "harness_smoke.py"
        if candidate.is_file():
            try:
                if needle in candidate.read_text(encoding="utf-8", errors="replace"):
                    return candidate
            except OSError:
                pass
    return None


def _read_ledger(mode: str, task_name: str) -> dict[str, Any]:
    plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
    path = agent_data_path(plan_dir, f"{task_name}.json")
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _check_acceptance(
    scenario: dict[str, Any],
    *,
    task_name: str,
    mode: str,
    mode_result: dict[str, Any] | None,
) -> list[str]:
    failures: list[str] = []
    acc = scenario.get("acceptance") or {}
    root = agent_data_path()

    needle = acc.get("file_contains")
    check_glob = acc.get("check_file_glob")
    if check_glob:
        matches = sorted(root.glob(check_glob), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches and needle and "harness_smoke" in check_glob:
            buf_hit = _code_project_harness_file(needle)
            if buf_hit is not None:
                matches = [buf_hit]
        if not matches:
            failures.append(f"expected file missing (glob {check_glob!r})")
        elif needle:
            try:
                text = matches[0].read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                failures.append(f"cannot read {matches[0]}: {exc}")
            else:
                if needle not in text:
                    failures.append(f"{matches[0]} does not contain {needle!r}")
    check_file = acc.get("check_file")
    if check_file:
        p = root / check_file if not Path(check_file).is_absolute() else Path(check_file)
        if not p.is_file():
            failures.append(f"expected file missing: {check_file}")
        elif needle:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                failures.append(f"cannot read {check_file}: {exc}")
            else:
                if needle not in text:
                    failures.append(f"{check_file} does not contain {needle!r}")

    min_del = int(acc.get("min_deliverable_chars") or 0)
    if min_del > 0:
        deliverable = (mode_result or {}).get("deliverable_path") if mode_result else None
        chars = 0
        if deliverable and Path(deliverable).is_file():
            try:
                chars = len(Path(deliverable).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        if chars < min_del:
            failures.append(f"deliverable {chars} chars < {min_del}")

    summary = str((mode_result or {}).get("summary") or "")
    if "OS Error" in summary or "charmap" in summary.lower():
        failures.append(f"run summary indicates failure: {summary[:200]}")

    ledger = _read_ledger(mode, task_name)
    if ledger:
        status = (ledger.get("status") or "").lower()
        steps = ledger.get("steps") or []
        all_pending = steps and all(
            (s.get("status") or "").lower() in ("pending", "") for s in steps
        )
        if status == "in_progress" and all_pending and (mode_result or {}).get("status") == "completed":
            failures.append("ledger stuck in_progress with all steps pending")
    return failures


def build_run_report(
    *,
    scenario_id: str,
    engine: str,
    task_name: str,
    mode_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge scorecard, task metrics, ledger, and mode result into one report."""
    scenario = get_scenario(scenario_id) or {}
    mode = (scenario.get("mode") or "task").strip().lower()
    rubric_key = scenario.get("rubric_key") or scenario_id

    jsonl = find_latest_jsonl(task_name)
    card = None
    if jsonl:
        card = score_jsonl_for_scenario(jsonl, rubric_key)
    metrics = get_task_metrics(mode, task_name)

    report: dict[str, Any] = {
        "scenario_id": scenario_id,
        "engine": engine,
        "mode": mode,
        "task_name": task_name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "jsonl_path": str(jsonl) if jsonl else None,
        "mode_result": mode_result,
        "metrics": metrics,
        "scorecard": card.to_dict() if card else None,
    }
    if card:
        report["wall_time_s"] = card.wall_time_s
        report["llm_turns"] = card.llm_responses
        report["tool_calls"] = card.tool_call_count
        report["tool_starts"] = card.tool_starts
        report["median_output_tokens_per_s"] = card.median_output_tokens_per_s
        report["total_output_tokens_est"] = card.total_output_tokens_est
        report["total_prompt_tokens_est"] = card.total_prompt_tokens_est
        report["scorecard_passed"] = card.passed
        report["scorecard_failures"] = card.failures
    if metrics.get("throughput"):
        report["throughput_health"] = metrics["throughput"].get("health")
    if mode_result:
        report["deliverable_path"] = mode_result.get("deliverable_path")
        report["run_status"] = mode_result.get("status")
    elif task_name:
        from .mode_runner import _guess_deliverable

        guessed = _guess_deliverable(mode, task_name)
        if guessed:
            report["deliverable_path"] = guessed
    return report


def evaluate_run(report: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (passed, failure reasons). Hard gate before advancing harness."""
    failures: list[str] = []
    scenario_id = report.get("scenario_id") or ""
    scenario = get_scenario(scenario_id) or {}
    task_name = report.get("task_name") or ""
    mode = report.get("mode") or scenario.get("mode") or "task"
    mode_result = report.get("mode_result")

    if report.get("run_status") not in ("completed", None):
        if report.get("run_status") in ("failed", "cancelled", "busy"):
            failures.append(f"mode_result status={report.get('run_status')}")

    if not report.get("jsonl_path"):
        failures.append("no JSONL log found for task")

    sc_failures = report.get("scorecard_failures") or []
    if sc_failures:
        failures.extend([f"scorecard: {x}" for x in sc_failures])
    elif report.get("scorecard_passed") is False:
        failures.append("scorecard rubric failed")

    mr = mode_result if isinstance(mode_result, dict) else None
    if mr is None and report.get("deliverable_path"):
        mr = {"deliverable_path": report.get("deliverable_path"), "status": report.get("run_status")}
    failures.extend(
        _check_acceptance(
            scenario,
            task_name=task_name,
            mode=mode,
            mode_result=mr,
        )
    )

    warnings: list[str] = []
    if report.get("throughput_health") == "slow":
        warnings.append("throughput_health=slow")
    report["warnings"] = warnings

    passed = not failures
    report["passed"] = passed
    report["failures"] = failures
    return passed, failures


def write_run_report(report: dict[str, Any]) -> Path:
    """Persist report JSON and append index.jsonl."""
    evaluate_run(report)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sid = report.get("scenario_id", "unknown")
    eng = report.get("engine", "unknown")
    out = _runs_dir() / f"{sid}_{eng}_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    index = _runs_dir() / "index.jsonl"
    with index.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": report.get("timestamp"),
                    "path": str(out),
                    "scenario_id": sid,
                    "engine": eng,
                    "passed": report.get("passed"),
                    "task_name": report.get("task_name"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    report["report_path"] = str(out)
    return out


def configure_engine(engine: str) -> tuple[bool, str]:
    """Point global Ollama client at stock or tq."""
    from agent.storage import DEFAULT_STOCK_URL, DEFAULT_TQ_URL, engine_for_base_url

    import agent.core.main as brain

    eng = (engine or "stock").strip().lower()
    if eng not in ("stock", "tq"):
        return False, f"unknown engine {engine!r}"
    url = DEFAULT_STOCK_URL if eng == "stock" else DEFAULT_TQ_URL
    brain.apply_runtime_settings(brain.client)
    brain.client.configure(base_url=url)
    # Harness TQ parity: disable native think on act turns (often slower / different stream).
    if eng == "tq" and not os.getenv("AQUILA_THINK_SURFACES"):
        os.environ["AQUILA_THINK_SURFACES"] = "chat,character,learn,explore,plan"
    if not brain.client.probe():
        return False, f"Ollama not reachable at {url}"
    return True, url


def run_scenario(
    scenario_id: str,
    *,
    engine: str = "stock",
    instance_id: str | None = None,
) -> dict[str, Any]:
    """Run one harness scenario; returns report dict (evaluate before advance)."""
    ensure_repo_cwd()
    clear_harness_stale_state()
    spec = get_scenario(scenario_id)
    if not spec:
        return {"ok": False, "error": f"unknown scenario {scenario_id!r}"}

    ok, msg = configure_engine(engine)
    if not ok:
        return {"ok": False, "error": msg, "engine": engine, "scenario_id": scenario_id}

    from .generation_lock import is_generation_busy, busy_payload

    if is_generation_busy():
        return {"ok": False, **busy_payload(), "scenario_id": scenario_id}

    inst = instance_id or spec.get("instance_id") or None
    from agent.storage import apply_instance_for_run
    from .mcp_attachments import load_attachments_for_mcp
    import agent.core.main as brain
    from .mode_runner import run_mode

    apply_instance_for_run(inst)
    configure_engine(engine)

    force_mp = spec.get("force_micro_plan")
    prev_force = os.environ.get("AQUILA_HARNESS_FORCE_MICRO_PLAN")
    prev_code_single = os.environ.get("AQUILA_MICRO_PLAN_CODE_SINGLE")
    if force_mp:
        os.environ["AQUILA_HARNESS_FORCE_MICRO_PLAN"] = "1"
    if spec.get("code_micro_single_step"):
        os.environ["AQUILA_MICRO_PLAN_CODE_SINGLE"] = "1"

    file_paths = spec.get("file_paths") or []
    fp_str = json.dumps(file_paths) if file_paths else ""
    text_chunks, image_payloads, ctx = load_attachments_for_mcp(
        fp_str,
        prefer_local=bool(spec.get("prefer_local")),
        context=spec.get("context") or "",
        mode=spec.get("mode") or "research",
    )
    agent = brain.get_agent(inst)
    try:
        result = run_mode(
            agent,
            mode=spec["mode"],
            objective=spec["objective"],
            context=ctx,
            text_chunks=text_chunks or None,
            image_payloads=image_payloads or None,
            generation_source="harness",
        )
    finally:
        if force_mp:
            if prev_force is None:
                os.environ.pop("AQUILA_HARNESS_FORCE_MICRO_PLAN", None)
            else:
                os.environ["AQUILA_HARNESS_FORCE_MICRO_PLAN"] = prev_force
        if spec.get("code_micro_single_step"):
            if prev_code_single is None:
                os.environ.pop("AQUILA_MICRO_PLAN_CODE_SINGLE", None)
            else:
                os.environ["AQUILA_MICRO_PLAN_CODE_SINGLE"] = prev_code_single
    mode_dict = result.to_dict()
    task_name = mode_dict.get("delegation_id") or mode_dict.get("task_name") or ""
    report = build_run_report(
        scenario_id=scenario_id,
        engine=engine,
        task_name=task_name,
        mode_result=mode_dict,
    )
    write_run_report(report)
    return {"ok": True, **report}


def run_matrix(
    *,
    engines: list[str] | None = None,
    scenario_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run scenarios x engines sequentially; return summary."""
    clear_harness_stale_state()
    engines = engines or ["stock", "tq"]
    scenario_ids = scenario_ids or list(HARNESS_SCENARIOS.keys())
    results: list[dict[str, Any]] = []
    failed = 0
    skipped = 0
    for eng in engines:
        ok_eng, _ = configure_engine(eng)
        if not ok_eng:
            for sid in scenario_ids:
                skipped += 1
                results.append(
                    {
                        "ok": False,
                        "skipped": True,
                        "engine": eng,
                        "scenario_id": sid,
                        "error": f"engine {eng} unreachable",
                    }
                )
            continue
        for sid in scenario_ids:
            rep = run_scenario(sid, engine=eng)
            if not rep.get("ok"):
                if "not reachable" in str(rep.get("error") or ""):
                    rep["skipped"] = True
                    skipped += 1
                else:
                    failed += 1
                results.append(rep)
                continue
            passed, _ = evaluate_run(rep)
            if not passed:
                failed += 1
            results.append(rep)
    return {
        "ok": failed == 0,
        "failed_count": failed,
        "skipped_count": skipped,
        "total": len(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: python capability_harness.py run_matrix [--engine stock|tq|both] [--scenario ID]")
        return 0
    cmd = argv[0]
    engines = ["stock", "tq"]
    scenarios = None
    i = 1
    while i < len(argv):
        if argv[i] == "--engine" and i + 1 < len(argv):
            eng = argv[i + 1].strip().lower()
            engines = ["stock", "tq"] if eng == "both" else [eng]
            i += 2
        elif argv[i] == "--scenario" and i + 1 < len(argv):
            scenarios = [argv[i + 1]]
            i += 2
        else:
            i += 1
    if cmd == "run_matrix":
        summary = run_matrix(engines=engines, scenario_ids=scenarios)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if summary.get("ok") else 1
    if cmd == "clear_lock":
        print(json.dumps(clear_harness_stale_state(), indent=2))
        return 0
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
