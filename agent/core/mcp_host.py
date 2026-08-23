"""Aquila MCP host — expose high-level meta-tools for Cursor and other MCP clients."""
from __future__ import annotations

import os

# MCP stdio: stdout is JSON-RPC only. Route human logs to stderr before any agent import.
os.environ.setdefault("AQUILA_STDIO_MCP_HOST", "1")

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .generation_lock import busy_payload, is_generation_busy, read_lock_info
from .stdio_safe import configure_stdio_utf8

configure_stdio_utf8()
from agent.storage import apply_instance_for_run
from .mcp_attachments import load_attachments_for_mcp
from agent.parser import get_task_metrics
from agent.storage import agent_data_path, ensure_repo_cwd

from .capability_harness import (
    build_run_report,
    clear_harness_stale_state,
    configure_engine,
    evaluate_run,
    get_scenario,
    list_scenarios,
    release_generation_lock_force,
    run_scenario as harness_run_scenario,
    write_run_report,
)

_DELIVERABLE_READ_CAP = int(os.getenv("AQUILA_MCP_DELIVERABLE_CAP", "12000"))
_RUN_MODES = frozenset({"research", "code", "writing", "task"})


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _mode_result_for_evaluate(
    task_name: str, mode: str
) -> dict[str, Any] | None:
    """Rebuild ModeResult-shaped dict for post-hoc evaluate (deliverable + status)."""
    from .capability_scorecard import find_latest_jsonl
    from .main import read_json_state
    from .mode_runner import ModeResult, _guess_deliverable
    from agent.storage import agent_data_path

    task = (task_name or "").strip()
    if not task:
        return None
    mode_norm = (mode or "task").strip().lower()
    plan_dir = "Agent-Plans" if mode_norm == "research" else "Agent-Tasks"
    ledger_path = str(agent_data_path(plan_dir, f"{task}.json"))
    status = "failed"
    summary = ""
    if Path(ledger_path).is_file():
        try:
            state = read_json_state(ledger_path)
            st = (state.get("status") or "").lower()
            if st == "completed":
                status = "completed"
            elif st == "in_progress":
                status = "in_progress"
            steps = state.get("steps") or []
            if steps and all(
                (s.get("status") or "").lower() == "completed" for s in steps
            ):
                status = "completed"
        except Exception:
            pass
    deliverable = _guess_deliverable(mode_norm, task)
    jsonl = find_latest_jsonl(task)
    if jsonl and status != "completed":
        try:
            tail = jsonl.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            if any("finish_task" in ln for ln in tail):
                status = "completed"
        except OSError:
            pass
    return ModeResult(
        status=status,
        mode=mode_norm,
        summary=summary,
        deliverable_path=deliverable,
        ledger_path=ledger_path,
        delegation_id=task,
    ).to_dict()


def _ensure_layout() -> None:
    ensure_repo_cwd()
    try:
        from .main import _ensure_data_layout

        _ensure_data_layout()
    except Exception:
        pass


def _resolve_ledger_path(mode: str, task_name: str) -> Path | None:
    try:
        from agent.gui import resolve_ledger_path

        return resolve_ledger_path(mode, task_name)
    except Exception:
        plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
        path = agent_data_path(plan_dir, f"{task_name}.json")
        return path if path.is_file() else None


def register_aquila_tools(mcp: FastMCP) -> None:
    """Register all Aquila meta-tools on a FastMCP instance."""

    @mcp.tool()
    def aquila_health(instance_id: str = "") -> str:
        """Check Ollama reachability, active model, instance, and generation lock."""
        _ensure_layout()
        apply_instance_for_run(instance_id or None)
        import main as brain

        client = brain.client
        model = getattr(client, "model_name", "") or ""
        base_url = getattr(client, "base_url", "") or ""
        reachable = False
        err = ""
        try:
            reachable = bool(getattr(client, "probe", lambda: False)())
        except Exception as exc:
            err = str(exc)
        lock = read_lock_info()
        return _json(
            {
                "ok": True,
                "ollama_reachable": reachable,
                "ollama_error": err,
                "model": model,
                "base_url": base_url,
                "instance_id": apply_instance_for_run(instance_id or None),
                "generation_busy": is_generation_busy(),
                "lock": lock.to_dict() if lock else None,
            }
        )

    @mcp.tool()
    def aquila_list_instances() -> str:
        """List Aquila instance profiles (id, display_name, default_mode, model)."""
        _ensure_layout()
        from agent.storage import list_instances

        rows = []
        for inst in list_instances():
            rows.append(
                {
                    "id": inst.id,
                    "display_name": inst.display_name,
                    "specialty": getattr(inst, "specialty", "") or "",
                    "default_mode": getattr(inst, "default_mode", "chat") or "chat",
                    "ollama_model": getattr(inst, "ollama_model", None),
                }
            )
        return _json({"instances": rows})

    @mcp.tool()
    def aquila_run_mode(
        mode: str,
        objective: str,
        context: str = "",
        instance_id: str = "",
        parent_task_id: str = "",
        file_paths: str = "",
        prefer_local: bool = False,
    ) -> str:
        """Run a headless Aquila mode loop (research|code|writing|task). Returns ModeResult JSON.

        file_paths: comma-separated or JSON list of repo-relative/absolute files to attach.
        prefer_local: hint the loop to use read_file/grep instead of web_search (local docs).
        For repo-only analysis, mode=code often works better than research.
        """
        _ensure_layout()
        mode_norm = (mode or "task").strip().lower()
        if mode_norm not in _RUN_MODES:
            return _json(
                {
                    "status": "failed",
                    "error": f"Invalid mode {mode!r}; use research, code, writing, or task.",
                }
            )
        if is_generation_busy():
            return _json(busy_payload())
        apply_instance_for_run(instance_id or None)
        import main as brain
        from .mode_runner import run_mode

        text_chunks, image_payloads, ctx = load_attachments_for_mcp(
            file_paths,
            prefer_local=prefer_local or mode_norm == "research",
            context=context,
        )
        agent = brain.get_agent(instance_id or None)
        result = run_mode(
            agent,
            mode=mode_norm,
            objective=objective,
            parent_task_id=parent_task_id or None,
            context=ctx,
            text_chunks=text_chunks or None,
            image_payloads=image_payloads or None,
            generation_source="mcp_host",
        )
        payload = result.to_dict()
        if text_chunks:
            payload["attached_files"] = len(text_chunks)
        return _json(payload)

    @mcp.tool()
    def aquila_run_autonomous(objective: str, instance_id: str = "") -> str:
        """Run a full Autonomous Task workflow locally. Returns summary + task_name."""
        _ensure_layout()
        if is_generation_busy():
            return _json(busy_payload())
        apply_instance_for_run(instance_id or None)
        import main as brain
        from remote.session import derive_task_name

        task_name = derive_task_name(objective)
        agent = brain.get_agent(instance_id or None)
        raw = agent.run_unified_task(
            task_name,
            objective,
            "task",
            generation_source="mcp_host",
        )
        status = "completed"
        if raw.startswith("🛑"):
            status = "busy" if "generation is running" in raw.lower() else "failed"
        return _json(
            {
                "status": status,
                "task_name": task_name,
                "summary": raw[:2048],
                "ledger_path": str(agent_data_path("Agent-Tasks", f"{task_name}.json")),
            }
        )

    @mcp.tool()
    def aquila_get_task_status(mode: str, task_name: str) -> str:
        """Read ledger JSON for a task (step index, status, steps summary)."""
        _ensure_layout()
        path = _resolve_ledger_path((mode or "task").strip().lower(), task_name)
        if not path or not path.is_file():
            return _json({"ok": False, "error": f"Ledger not found for {task_name!r}"})
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return _json({"ok": False, "error": str(exc)})
        steps = state.get("steps") or []
        return _json(
            {
                "ok": True,
                "path": str(path),
                "status": state.get("status"),
                "current_step_index": state.get("current_step_index"),
                "steps": [
                    {
                        "step_kind": s.get("step_kind"),
                        "status": s.get("status"),
                        "description": (s.get("description") or "")[:200],
                    }
                    for s in steps
                ],
            }
        )

    @mcp.tool()
    def aquila_get_task_metrics(mode: str, task_name: str) -> str:
        """Live throughput from Agent-Logs JSONL: tokens/s, slow detection, ETA from ledger."""
        _ensure_layout()
        return _json(get_task_metrics(mode, task_name))

    @mcp.tool()
    def aquila_probe_throughput(
        instance_id: str = "",
        engine: str = "active",
    ) -> str:
        """Quick streaming probe: tokens/s vs baseline. engine: active|stock|tq|both."""
        _ensure_layout()
        apply_instance_for_run(instance_id or None)
        import main as brain
        from agent.parser import quick_throughput_probe
        from agent.storage import DEFAULT_STOCK_URL, DEFAULT_TQ_URL, engine_base_urls

        engine_norm = (engine or "active").strip().lower()
        prompt = "Reply with one short sentence."

        def _probe_client(client) -> dict:
            return quick_throughput_probe(
                client,
                prompt=prompt,
                warmup=False,
                timeout_s=int(os.getenv("AQUILA_PROBE_TIMEOUT_S", "120") or "120"),
            )

        if engine_norm == "both":
            results = {}
            for eng, url in engine_base_urls().items():
                probe_client = brain.client
                probe_client.configure(base_url=url)
                results[eng] = _probe_client(probe_client)
            apply_instance_for_run(instance_id or None)
            return _json({"ok": True, "engines": results})

        if engine_norm in ("stock", "tq"):
            url = DEFAULT_STOCK_URL if engine_norm == "stock" else DEFAULT_TQ_URL
            brain.client.configure(base_url=url)
        return _json(_probe_client(brain.client))

    @mcp.tool()
    def aquila_list_scenarios(mode: str = "") -> str:
        """List harness scenarios (optional filter: research|code|writing|task)."""
        _ensure_layout()
        return _json({"scenarios": list_scenarios(mode=mode or None)})

    @mcp.tool()
    def aquila_run_scenario(
        scenario_id: str,
        engine: str = "stock",
        instance_id: str = "",
    ) -> str:
        """Run a predefined harness scenario on stock or tq Ollama. Returns report JSON."""
        _ensure_layout()
        if is_generation_busy():
            return _json(busy_payload())
        if not get_scenario(scenario_id):
            return _json({"ok": False, "error": f"Unknown scenario {scenario_id!r}"})
        rep = harness_run_scenario(
            scenario_id,
            engine=engine,
            instance_id=instance_id or None,
        )
        return _json(rep)

    @mcp.tool()
    def aquila_evaluate_run(
        mode: str,
        task_name: str,
        scenario_id: str,
        engine: str = "stock",
    ) -> str:
        """Build report, apply rubric, write Agent-Logs/capability-runs/*.json."""
        _ensure_layout()
        spec = get_scenario(scenario_id) or {}
        mode_result = _mode_result_for_evaluate(task_name, spec.get("mode") or mode)
        report = build_run_report(
            scenario_id=scenario_id,
            engine=engine,
            task_name=task_name,
            mode_result=mode_result,
        )
        passed, failures = evaluate_run(report)
        path = write_run_report(report)
        return _json(
            {
                "ok": True,
                "passed": passed,
                "failures": failures,
                "report_path": str(path),
                "report": report,
            }
        )

    @mcp.tool()
    def aquila_release_generation_lock() -> str:
        """Clear stale generation lock or release lock held by this process."""
        _ensure_layout()
        return _json(release_generation_lock_force())

    @mcp.tool()
    def aquila_read_deliverable(path: str, max_chars: int = 0) -> str:
        """Read a deliverable markdown file (bounded). Use path from aquila_run_mode result."""
        _ensure_layout()
        cap = max_chars if max_chars and max_chars > 0 else _DELIVERABLE_READ_CAP
        cap = min(cap, 100_000)
        raw_path = (path or "").strip()
        if not raw_path:
            return _json({"ok": False, "error": "path is required"})
        p = Path(raw_path)
        if not p.is_file():
            return _json({"ok": False, "error": f"File not found: {raw_path}"})
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return _json({"ok": False, "error": str(exc)})
        truncated = len(text) > cap
        if truncated:
            text = text[:cap] + f"\n\n...[truncated at {cap} chars]"
        return _json(
            {
                "ok": True,
                "path": str(p.resolve()),
                "chars": len(text),
                "truncated": truncated,
                "content": text,
            }
        )

    @mcp.tool()
    def aquila_list_research_capabilities() -> str:
        """List registered research capability modules."""
        from agent.capabilities import list_capabilities

        caps = list_capabilities(mode="research")
        return _json([
            {
                "id": c.capability_id,
                "title": c.title,
                "tier": c.tier,
                "description": c.description,
            }
            for c in caps
        ])

    @mcp.tool()
    def aquila_run_research_capability(
        capability_id: str,
        arguments_json: str = "{}",
        task_id: str = "mcp_research",
    ) -> str:
        """Run one research capability by ID with JSON arguments."""
        from agent.capabilities import run_capability
        from agent.capabilities.base import CapabilityContext
        from agent.storage import get_memory

        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return _json({"ok": False, "error": f"Invalid arguments_json: {exc}"})
        if not isinstance(args, dict):
            return _json({"ok": False, "error": "arguments_json must be a JSON object"})
        ctx = CapabilityContext(
            client=None,
            memory=get_memory(),
            task_id=task_id,
            mode="research",
        )
        result = run_capability(capability_id.strip(), ctx, args)
        return _json({
            "ok": result.ok,
            "summary": result.summary,
            "data": result.data,
            "error_code": result.error_code,
            "error_message": result.error_message,
        })


def create_aquila_mcp(
    name: str = "aquila",
    *,
    transport_security: TransportSecuritySettings | None = None,
) -> FastMCP:
    mcp = FastMCP(
        name,
        instructions=(
            "Aquila local agent host. Delegate heavy research/code/writing to local Ollama. "
            "Use aquila_run_scenario / aquila_evaluate_run for harness loops; "
            "aquila_get_task_metrics for live tokens/s; aquila_probe_throughput for speed checks."
        ),
        transport_security=transport_security,
    )
    register_aquila_tools(mcp)
    return mcp


def main(argv: list[str] | None = None) -> None:
    configure_stdio_utf8()
    argv = list(argv or sys.argv[1:])
    transport = "stdio"
    port = 8765
    if "--sse" in argv:
        transport = "sse"
        argv.remove("--sse")
    if "--port" in argv:
        idx = argv.index("--port")
        port = int(argv[idx + 1])
        del argv[idx : idx + 2]
    mcp = create_aquila_mcp()
    if transport == "sse":
        import uvicorn

        app = mcp.sse_app()
        uvicorn.run(app, host="127.0.0.1", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
