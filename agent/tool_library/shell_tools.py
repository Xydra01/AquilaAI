"""Scoped terminal commands for Code Mode (Aquila 3.4 Wave 4)."""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from tool_library.code_canvas_tools import get_active_project_scope

_BLOCKED_PATTERNS = re.compile(
    r"(?:\||;|&&|\$\(|`|\brm\b|\bdel\b|>\s*|\bformat\b|\bcurl\b.*\||powershell\s+-enc)",
    re.I,
)

_ALLOWLIST_PREFIXES = (
    "pytest",
    "python -m pytest",
    "flake8",
    "git status",
    "git diff",
    "git log",
    "pip list",
    "pip show",
    "npm test",
    "npm run",
    "cargo test",
    "go test",
)


def _terminal_enabled() -> bool:
    return os.getenv("AQUILA_TERMINAL", "0").strip().lower() in ("1", "true", "yes", "on")


def _log_terminal(instance_id: str, command: str, cwd: str, output: str) -> None:
    from workspace_paths import agent_data_path

    log_dir = agent_data_path("Agent-Logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    iid = instance_id or "default"
    path = log_dir / f"terminal_{iid}.log"
    stamp = datetime.now().isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n--- {stamp} cwd={cwd} ---\n> {command}\n{output}\n")


def _resolve_cwd(cwd: str | None) -> Path | None:
    scope = get_active_project_scope()
    if not scope:
        return None
    root = Path(scope["root"]).resolve()
    if cwd:
        target = (root / cwd).resolve()
    else:
        target = root
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def run_terminal_command(command: str, cwd: str = ".", timeout: int = 120) -> str:
    """
    Run an allowlisted shell command inside the active code project root.
    Requires AQUILA_TERMINAL=1. Blocks pipes, redirects, and destructive commands.
    """
    if not _terminal_enabled():
        return "❌ Terminal tool disabled. Set AQUILA_TERMINAL=1 in .env to enable."

    cmd = (command or "").strip()
    if not cmd:
        return "❌ Empty command."
    if _BLOCKED_PATTERNS.search(cmd):
        return "❌ Command blocked by security policy (shell metacharacters or risky verbs)."
    if not any(cmd.lower().startswith(p) for p in _ALLOWLIST_PREFIXES):
        return (
            "❌ Command not on allowlist. Permitted prefixes: "
            + ", ".join(_ALLOWLIST_PREFIXES[:6])
            + ", ..."
        )

    workdir = _resolve_cwd(cwd)
    if workdir is None:
        return "❌ No active code project or cwd outside project root."

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=min(max(5, timeout), 300),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        from instance_registry import get_active_instance_id

        _log_terminal(get_active_instance_id(), cmd, str(workdir), out[:8000])
        status = "✅" if proc.returncode == 0 else "⚠️"
        return f"{status} exit={proc.returncode}\n{out[:6000]}"
    except subprocess.TimeoutExpired:
        return f"❌ Command timed out after {timeout}s."
    except Exception as e:
        return f"❌ Terminal error: {e}"


SHELL_TOOLS = {
    "run_terminal_command": {
        "func": run_terminal_command,
        "description": run_terminal_command.__doc__,
    },
}
