"""Read-only git introspection for code mode."""
from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

from tools import get_code_project_root
from tool_result import format_tool_result

_MAX_OUT = 12_000


def _git_cwd() -> Path | None:
    root = get_code_project_root()
    if root and (root / ".git").exists():
        return root
    return None


def _run_git(args: list[str]) -> tuple[int, str]:
    cwd = _git_cwd()
    if not cwd:
        return 1, "No git repository at CODE_PROJECT_ROOT"
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out
    except Exception as e:
        return 1, str(e)


def git_status() -> str:
    """
    Show git status for the open code project.
    USE WHEN: before commits or to see modified files.
    """
    code, out = _run_git(["status", "--short", "--branch"])
    out = out[:_MAX_OUT]
    if code != 0:
        return format_tool_result("ERROR", "git status failed", out)
    return format_tool_result("OK", "git status", out or "(clean)")


def git_diff(file_path: str = "") -> str:
    """
    Show git diff for the project or one file.
    USE WHEN: reviewing changes before sync or after edits.
    """
    args = ["diff", "--stat"]
    if file_path and str(file_path).strip():
        args = ["diff", "--", str(file_path).strip()]
    code, out = _run_git(args)
    out = out[:_MAX_OUT]
    if code != 0 and "not a git" not in out.lower():
        return format_tool_result("WARN", "git diff", out)
    return format_tool_result("OK", "git diff", out or "(no changes)")


def find_references(symbol: str, path: str = ".") -> str:
    """
    Find lines mentioning a symbol name (lite reference search).
    USE WHEN: tracing usages after read_code_outline.
    """
    from tool_library.grep_tools import grep_repo

    return grep_repo(pattern=symbol, path=path, glob="*.py", max_matches=40)


GIT_TOOLS = {
    "git_status": {"func": git_status, "description": inspect.getdoc(git_status)},
    "git_diff": {"func": git_diff, "description": inspect.getdoc(git_diff)},
    "find_references": {"func": find_references, "description": inspect.getdoc(find_references)},
}
