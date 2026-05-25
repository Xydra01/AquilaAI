"""Scoped command execution for code/task modes."""
from __future__ import annotations

import inspect
import os
import shlex
import subprocess
from pathlib import Path

from tools import get_code_project_root, is_safe_path, resolve_tool_path
from tool_result import format_tool_result

_ALLOW_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python -m",
    "npm ",
    "npx ",
    "git ",
    "flake8",
    "ruff ",
    "mypy ",
    "cargo ",
    "go test",
    "go build",
)


def _run_command_enabled() -> bool:
    return os.getenv("AQUILA_RUN_COMMAND", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def run_command(command: str, cwd: str = "", timeout_seconds: int = 120) -> str:
    """
    Run an allowlisted shell command in the code project or task cwd.
    USE WHEN: pytest, npm, git, linters — not for interactive shells.
    Requires AQUILA_RUN_COMMAND=1 (default on).
    """
    if not _run_command_enabled():
        return format_tool_result(
            "ERROR",
            "run_command disabled. Set AQUILA_RUN_COMMAND=1 in .env",
        )

    cmd = (command or "").strip()
    if not cmd:
        return format_tool_result("ERROR", "command is required")

    low = cmd.lower()
    if not any(low.startswith(p) for p in _ALLOW_PREFIXES):
        return format_tool_result(
            "ERROR",
            f"Command not allowlisted. Allowed prefixes: {', '.join(_ALLOW_PREFIXES[:6])}...",
        )

    if ";" in cmd or "|" in cmd or ">" in cmd or "<" in cmd and "pytest" not in low:
        if "|" in cmd or ";" in cmd:
            return format_tool_result("ERROR", "Pipes and command chaining are blocked")

    try:
        timeout_seconds = int(timeout_seconds)
    except (TypeError, ValueError):
        timeout_seconds = 120
    timeout_seconds = max(10, min(timeout_seconds, 600))

    work = get_code_project_root()
    if cwd and str(cwd).strip():
        work = resolve_tool_path(cwd)
    if not work or not Path(work).exists():
        work = Path.cwd()
    if not is_safe_path(Path(work)):
        return format_tool_result("ERROR", "cwd is not allowed")

    try:
        args = shlex.split(cmd, posix=os.name != "nt")
        r = subprocess.run(
            args,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        out = ((r.stdout or "") + (r.stderr or ""))[:12000]
        status = "OK" if r.returncode == 0 else "WARN"
        return format_tool_result(status, f"exit {r.returncode}", out)
    except subprocess.TimeoutExpired:
        return format_tool_result("ERROR", f"Command timed out after {timeout_seconds}s")
    except Exception as e:
        return format_tool_result("ERROR", str(e))


RUN_TOOLS = {
    "run_command": {"func": run_command, "description": inspect.getdoc(run_command)},
}
