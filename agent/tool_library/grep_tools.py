"""Unified repo search (replaces most search_files / search_in_file usage)."""
from __future__ import annotations

import fnmatch
import inspect
import os
from pathlib import Path

from tools import is_safe_path, resolve_tool_path, should_skip_dir
from tool_result import format_tool_result


def grep_repo(
    pattern: str,
    path: str = ".",
    glob: str = "*",
    max_matches: int = 50,
) -> str:
    """
    Search file contents under path for pattern (case-insensitive substring).
    USE WHEN: find symbols, strings, or usages across the project.
    DO NOT USE: for filename-only discovery — use search_files or get_directory_tree.
    """
    try:
        max_matches = int(max_matches)
    except (TypeError, ValueError):
        max_matches = 50
    max_matches = max(1, min(max_matches, 200))

    root = resolve_tool_path(path or ".")
    if not is_safe_path(root):
        return format_tool_result("ERROR", f"Security block: {path}")

    if not root.exists():
        return format_tool_result("ERROR", f"Path not found: {path}")

    pat = (pattern or "").strip()
    if not pat:
        return format_tool_result("ERROR", "pattern is required")

    glob_pat = (glob or "*").strip()
    matches: list[str] = []
    needle = pat.lower()

    if root.is_file():
        files = [root]
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
            for fname in filenames:
                if fnmatch.fnmatch(fname, glob_pat):
                    files.append(Path(dirpath) / fname)

    for fpath in files:
        if len(matches) >= max_matches:
            break
        try:
            if not is_safe_path(fpath):
                continue
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                try:
                    rel = fpath.relative_to(root if root.is_dir() else fpath.parent)
                except ValueError:
                    rel = fpath.name
                matches.append(f"{rel}:{i}: {line.strip()[:200]}")
                if len(matches) >= max_matches:
                    break

    if not matches:
        return format_tool_result("OK", f"No matches for '{pat}' under {path}")
    body = "\n".join(matches)
    if len(matches) >= max_matches:
        body += f"\n... capped at {max_matches} matches"
    return format_tool_result("OK", f"{len(matches)} match(es) for '{pat}'", body)


def apply_patch(file_path: str, patch_text: str) -> str:
    """Alias entry point for apply_unified_patch (shorter schema name)."""
    from tool_library.code_canvas_tools import apply_unified_patch

    return apply_unified_patch(file_path, patch_text)


GREP_TOOLS = {
    "grep_repo": {"func": grep_repo, "description": inspect.getdoc(grep_repo)},
    "apply_patch": {"func": apply_patch, "description": "Apply a unified diff patch to a file in the code project (alias for apply_unified_patch)."},
}
