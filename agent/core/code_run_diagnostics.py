"""Diagnostics for live Aquila code-mode runs (JSONL logs + Code Canvas state)."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.storage import agent_data_path


@dataclass
class StallSignal:
    kind: str
    count: int
    detail: str


@dataclass
class CodeRunDiagnostic:
    task_name: str
    jsonl_path: str | None = None
    events: int = 0
    llm_turns: int = 0
    capability_calls: list[str] = field(default_factory=list)
    capability_failures: list[str] = field(default_factory=list)
    forced_advances: int = 0
    parse_failures: int = 0
    stall_signals: list[StallSignal] = field(default_factory=list)
    last_events: list[dict[str, Any]] = field(default_factory=list)
    code_state: dict[str, Any] = field(default_factory=dict)
    buffer_files: list[str] = field(default_factory=list)
    on_disk_files: list[str] = field(default_factory=list)
    habit_tracker_ok: bool = False
    habit_failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "jsonl_path": self.jsonl_path,
            "events": self.events,
            "llm_turns": self.llm_turns,
            "capability_calls": self.capability_calls[-30:],
            "capability_failures": self.capability_failures[-20:],
            "forced_advances": self.forced_advances,
            "parse_failures": self.parse_failures,
            "stall_signals": [
                {"kind": s.kind, "count": s.count, "detail": s.detail}
                for s in self.stall_signals
            ],
            "last_events": self.last_events,
            "buffer_files": self.buffer_files,
            "on_disk_files": self.on_disk_files,
            "habit_tracker_ok": self.habit_tracker_ok,
            "habit_failures": self.habit_failures,
        }


def load_active_code_state() -> dict[str, Any]:
    path = agent_data_path("Agent-Code", "active_code_state.json")
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _buffer_file_paths(state: dict[str, Any]) -> list[str]:
    files = state.get("files") or []
    paths: list[str] = []
    if isinstance(files, dict):
        paths = [str(k) for k in files.keys()]
    elif isinstance(files, list):
        for entry in files:
            if isinstance(entry, dict) and entry.get("path"):
                paths.append(str(entry["path"]))
    return sorted(paths)


def _on_disk_project_files(state: dict[str, Any]) -> list[str]:
    root = (state.get("root") or "").strip()
    if not root:
        return []
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    found: list[str] = []
    for p in root_path.rglob("*"):
        if p.is_file() and p.name not in (".gitkeep",):
            try:
                found.append(str(p.relative_to(root_path)).replace("\\", "/"))
            except ValueError:
                found.append(str(p))
    return sorted(found)


def check_habit_tracker_project(
    *,
    state: dict[str, Any] | None = None,
    buffer_paths: list[str] | None = None,
    disk_paths: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Verify habit-tracker deliverables in buffer and/or on disk."""
    state = state or load_active_code_state()
    buffer_paths = buffer_paths if buffer_paths is not None else _buffer_file_paths(state)
    disk_paths = disk_paths if disk_paths is not None else _on_disk_project_files(state)
    all_paths = {p.replace("\\", "/") for p in buffer_paths + disk_paths}
    failures: list[str] = []

    def _has(path_suffix: str) -> bool:
        return any(p.endswith(path_suffix) or p == path_suffix for p in all_paths)

    required = ("habit.py", "tests/test_habit.py", "README.md")
    for req in required:
        if not _has(req):
            failures.append(f"missing {req}")

    habit_text = ""
    for rel in all_paths:
        norm = rel.replace("\\", "/")
        if norm == "habit.py" or norm.endswith("/habit.py"):
            if "/tests/" in norm or norm.startswith("tests/"):
                continue
            habit_text = _read_project_file(state, norm) or ""
            break
    if habit_text:
        for kw in ("add", "done", "list"):
            if kw not in habit_text.lower():
                failures.append(f"habit.py missing subcommand hint: {kw}")
        if "habits.json" not in habit_text.lower():
            failures.append("habit.py does not reference habits.json storage")
    elif not failures:
        failures.append("habit.py content not readable")

    test_text = ""
    for rel in all_paths:
        if rel.endswith("tests/test_habit.py"):
            test_text = _read_project_file(state, rel) or ""
            break
    if test_text and "def test" not in test_text and "pytest" not in test_text.lower():
        failures.append("tests/test_habit.py does not look like pytest tests")

    return not failures, failures


def _read_project_file(state: dict[str, Any], rel_path: str) -> str | None:
    files = state.get("files") or []
    norm = rel_path.replace("\\", "/")
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict):
                continue
            p = str(entry.get("path") or "").replace("\\", "/")
            if p == norm or p.endswith("/" + norm):
                return str(entry.get("content") or "")
    elif isinstance(files, dict):
        for key, val in files.items():
            k = str(key).replace("\\", "/")
            if k == norm or k.endswith("/" + norm):
                if isinstance(val, dict):
                    return str(val.get("content") or "")
                return str(val)
    root = (state.get("root") or "").strip()
    if root:
        candidate = Path(root) / norm
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def _cap_id_from_event(row: dict[str, Any]) -> str:
    for key in ("cap_id", "capability_id", "tool_name"):
        val = row.get(key) or ""
        if val:
            return str(val)
    body = str(row.get("body") or row.get("preview") or "")
    m = re.search(r"cap\.[a-z0-9_.@-]+", body, re.I)
    return m.group(0) if m else ""


def analyze_jsonl(path: str | Path, *, tail: int = 12) -> dict[str, Any]:
    """Parse a run JSONL into counters useful for stall triage."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"missing jsonl: {p}"}
    caps: list[str] = []
    failures: list[str] = []
    forced = 0
    parse_fail = 0
    llm_turns = 0
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        rows.append(row)
        ev = str(row.get("event") or "")
        if ev == "llm_response":
            llm_turns += 1
        elif ev == "forced_advance":
            forced += 1
        elif ev == "structured_parse" and not row.get("ok"):
            parse_fail += 1
        elif ev in ("tool_start", "tool_end", "run_state_checkpoint"):
            cap = _cap_id_from_event(row)
            if cap.startswith("cap."):
                caps.append(cap)
            if ev == "run_state_checkpoint" and row.get("ok") is False:
                failures.append(f"{cap}: {(row.get('summary') or '')[:120]}")
            if ev == "tool_end" and row.get("ok") is False:
                failures.append(f"{cap}: {(row.get('preview') or '')[:120]}")

    stall_signals = detect_stall_signals(caps, failures)
    return {
        "ok": True,
        "events": len(rows),
        "llm_turns": llm_turns,
        "capability_calls": caps,
        "capability_failures": failures,
        "forced_advances": forced,
        "parse_failures": parse_fail,
        "stall_signals": [s.__dict__ for s in stall_signals],
        "last_events": rows[-tail:],
    }


def detect_stall_signals(
    capability_calls: list[str],
    capability_failures: list[str] | None = None,
) -> list[StallSignal]:
    """Heuristic stall patterns from capability call sequences."""
    signals: list[StallSignal] = []
    counts = Counter(capability_calls)
    for cap, n in counts.most_common(5):
        if n >= 4:
            signals.append(StallSignal("repeat_capability", n, cap))

    create_n = counts.get("cap.dev.create_file@v1", 0)
    if create_n >= 3:
        signals.append(
            StallSignal("create_file_loop", create_n, "cap.dev.create_file@v1")
        )

    failures = capability_failures or []
    exists_blocks = sum(
        1 for f in failures if "exists" in f.lower() or "OS BLOCK" in f
    )
    if exists_blocks >= 2:
        signals.append(
            StallSignal("exists_block_loop", exists_blocks, "create_file exists")
        )
    missing_content = sum(1 for f in failures if "content" in f.lower())
    if missing_content >= 2:
        signals.append(
            StallSignal("missing_content_loop", missing_content, "create_file content")
        )

    recon_n = counts.get("cap.dev.recon@v1", 0)
    if recon_n >= 3:
        signals.append(StallSignal("recon_thrash", recon_n, "cap.dev.recon@v1"))

    return signals


def diagnose_code_run(task_name: str, *, jsonl_path: str | Path | None = None) -> CodeRunDiagnostic:
    """Full diagnostic snapshot for a code-mode task."""
    from .capability_scorecard import find_latest_jsonl

    diag = CodeRunDiagnostic(task_name=task_name)
    path = Path(jsonl_path) if jsonl_path else find_latest_jsonl(task_name)
    if path and path.is_file():
        diag.jsonl_path = str(path)
        parsed = analyze_jsonl(path)
        if parsed.get("ok"):
            diag.events = int(parsed.get("events") or 0)
            diag.llm_turns = int(parsed.get("llm_turns") or 0)
            diag.capability_calls = list(parsed.get("capability_calls") or [])
            diag.capability_failures = list(parsed.get("capability_failures") or [])
            diag.forced_advances = int(parsed.get("forced_advances") or 0)
            diag.parse_failures = int(parsed.get("parse_failures") or 0)
            diag.last_events = list(parsed.get("last_events") or [])
            diag.stall_signals = [
                StallSignal(**s) for s in (parsed.get("stall_signals") or [])
            ]

    state = load_active_code_state()
    diag.code_state = {
        "project_name": state.get("project_name"),
        "root": state.get("root"),
        "workspace_mode": state.get("workspace_mode"),
    }
    diag.buffer_files = _buffer_file_paths(state)
    diag.on_disk_files = _on_disk_project_files(state)
    ok, fails = check_habit_tracker_project(
        state=state,
        buffer_paths=diag.buffer_files,
        disk_paths=diag.on_disk_files,
    )
    diag.habit_tracker_ok = ok
    diag.habit_failures = fails
    return diag


def format_diagnostic_report(diag: CodeRunDiagnostic) -> str:
    lines = [
        f"Task: {diag.task_name}",
        f"JSONL: {diag.jsonl_path or '(none)'}",
        f"Events: {diag.events} | LLM turns: {diag.llm_turns} | "
        f"Forced advances: {diag.forced_advances} | Parse failures: {diag.parse_failures}",
        f"Code project: {diag.code_state.get('root') or '(none)'}",
        f"Buffer files ({len(diag.buffer_files)}): {', '.join(diag.buffer_files[:12])}",
    ]
    if diag.on_disk_files:
        lines.append(
            f"On-disk files ({len(diag.on_disk_files)}): "
            + ", ".join(diag.on_disk_files[:12])
        )
    if diag.stall_signals:
        lines.append("Stall signals:")
        for s in diag.stall_signals:
            lines.append(f"  - {s.kind} x{s.count}: {s.detail}")
    if diag.capability_failures:
        lines.append("Recent capability failures:")
        for f in diag.capability_failures[-5:]:
            lines.append(f"  - {f[:160]}")
    lines.append(
        f"Habit tracker OK: {diag.habit_tracker_ok}"
        + (f" ({'; '.join(diag.habit_failures)})" if diag.habit_failures else "")
    )
    return "\n".join(lines)
