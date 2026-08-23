"""Headless mode execution wrapper for Autonomous 4.0 delegation."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.storage import agent_data_path


@dataclass
class ModeResult:
    status: str  # completed | failed | cancelled
    mode: str
    summary: str
    deliverable_path: str | None
    ledger_path: str
    metrics: dict[str, Any] = field(default_factory=dict)
    delegation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModeResult:
        return cls(
            status=str(data.get("status", "failed")),
            mode=str(data.get("mode", "")),
            summary=str(data.get("summary", ""))[:2048],
            deliverable_path=data.get("deliverable_path"),
            ledger_path=str(data.get("ledger_path", "")),
            metrics=dict(data.get("metrics") or {}),
            delegation_id=str(data.get("delegation_id", "")),
        )


def delegation_dir(parent_task_id: str) -> Path:
    root = agent_data_path("Agent-Tasks") / parent_task_id / "delegations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def delegation_artifacts_dir(parent_task_id: str) -> Path:
    root = agent_data_path("Agent-Tasks") / parent_task_id / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_delegation_task_name(parent_task_id: str, mode: str) -> str:
    ts = int(time.time())
    safe_mode = (mode or "task").replace("/", "_")[:24]
    return f"{safe_mode}_{ts}"


def resolve_nested_task_file(
    *,
    mode: str,
    task_name: str,
    parent_task_id: str | None,
) -> tuple[str, str]:
    """Return (plan_dir, task_file path string)."""
    if parent_task_id:
        ddir = delegation_dir(parent_task_id)
        task_file = str(ddir / f"{task_name}.json")
        plan_dir = str(ddir)
        meta = ddir / f"{task_name}.meta.json"
        meta.write_text(
            json.dumps(
                {"parent_task_id": parent_task_id, "mode": mode, "task_name": task_name},
                indent=2,
            ),
            encoding="utf-8",
        )
        return plan_dir, task_file
    plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
    return plan_dir, str(agent_data_path(plan_dir, f"{task_name}.json"))


def run_mode(
    agent,
    *,
    mode: str,
    objective: str,
    task_name: str | None = None,
    parent_task_id: str | None = None,
    context: str = "",
    ui_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    text_chunks: list | None = None,
    image_payloads: list | None = None,
    generation_source: str = "task",
) -> ModeResult:
    """Run a full mode loop headlessly and return structured ModeResult."""
    mode_norm = (mode or "task").strip().lower()
    if mode_norm in ("autonomous", "task") and parent_task_id:
        mode_norm = "task"
    task_name = task_name or make_delegation_task_name(
        parent_task_id or "standalone", mode_norm
    )
    user_request = objective.strip()
    if context.strip():
        user_request = f"{user_request}\n\nContext from prior step:\n{context.strip()}"

    started = time.monotonic()
    ledger_path = ""
    try:
        plan_dir, ledger_path = resolve_nested_task_file(
            mode=mode_norm,
            task_name=task_name,
            parent_task_id=parent_task_id,
        )
        if parent_task_id:
            init_res = ModeResult(
                status="running",
                mode=mode_norm,
                summary="Running delegation...",
                deliverable_path=None,
                ledger_path=ledger_path,
                metrics={"parent_task_id": parent_task_id},
                delegation_id=task_name,
            )
            _persist_mode_result(parent_task_id, init_res)
        result_text = agent.run_unified_task(
            task_name=task_name,
            user_request=user_request,
            mode=mode_norm,
            ui_callback=ui_callback,
            cancel_check=cancel_check,
            text_chunks=text_chunks,
            image_payloads=image_payloads,
            parent_task_id=parent_task_id,
            plan_dir_override=plan_dir,
            task_file_override=ledger_path,
            generation_source=generation_source,
        )
    except Exception as exc:
        return ModeResult(
            status="failed",
            mode=mode_norm,
            summary=str(exc)[:2048],
            deliverable_path=None,
            ledger_path=ledger_path,
            metrics={"wall_time_s": round(time.monotonic() - started, 2)},
            delegation_id=task_name,
        )

    from agent.core.task_artifacts import extract_plan_review_result

    if cancel_check and cancel_check():
        status = "cancelled"
    elif extract_plan_review_result(result_text):
        status = "in_progress"
    elif result_text.startswith("🛑"):
        status = "cancelled"
    elif "❌" in result_text[:120] or "failed" in result_text.lower()[:120]:
        status = "failed"
    else:
        status = "completed"

    deliverable = _guess_deliverable(mode_norm, task_name)
    summary = _summarize_result(result_text, deliverable)
    metrics = {
        "wall_time_s": round(time.monotonic() - started, 2),
        "parent_task_id": parent_task_id or "",
    }

    mode_result = ModeResult(
        status=status,
        mode=mode_norm,
        summary=summary,
        deliverable_path=deliverable,
        ledger_path=ledger_path,
        metrics=metrics,
        delegation_id=task_name,
    )
    if parent_task_id:
        _persist_mode_result(parent_task_id, mode_result)
    return mode_result


def _guess_deliverable(mode: str, task_name: str) -> str | None:
    candidates = []
    if mode == "research":
        candidates.append(agent_data_path("Agent-Research", f"{task_name}.md"))
    elif mode == "writing":
        candidates.append(agent_data_path("Agent-Drafts", f"{task_name}.md"))
    else:
        candidates.append(agent_data_path("Agent-Creations", f"{task_name}.md"))
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _summarize_result(result_text: str, deliverable: str | None) -> str:
    lines = [result_text.strip()]
    if deliverable:
        lines.append(f"Deliverable: {deliverable}")
    summary = "\n".join(lines)
    return summary[:2048]


def _persist_mode_result(parent_task_id: str, result: ModeResult) -> None:
    art_dir = delegation_artifacts_dir(parent_task_id)
    out = art_dir / f"{result.delegation_id}.mode_result.json"
    out.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def load_delegation_stack(parent_task_id: str) -> list[ModeResult]:
    art_dir = delegation_artifacts_dir(parent_task_id)
    if not art_dir.is_dir():
        return []
    results: list[ModeResult] = []
    for path in sorted(art_dir.glob("*.mode_result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(ModeResult.from_dict(data))
        except (json.JSONDecodeError, OSError):
            continue
    return results
