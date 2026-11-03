"""Code mode context: project snapshot and auto-context after grep."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from agent.core import get_code_project_root, is_ignored_code_path, should_skip_dir
from agent.core.tools import get_directory_tree

_KEY_EXTENSIONS = (".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt")
_MAX_KEY_FILES = 40

_GREP_HIT_RE = re.compile(r"^([^:]+):(\d+):\s*(.*)$")


def snapshot_max_chars() -> int:
    raw = os.getenv("AQUILA_CODE_SNAPSHOT_MAX_CHARS", "8000").strip()
    try:
        return max(500, int(raw))
    except ValueError:
        return 8000


def auto_context_enabled() -> bool:
    return os.getenv("AQUILA_CODE_AUTO_CONTEXT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def auto_context_max_chars() -> int:
    raw = os.getenv("AQUILA_CODE_AUTO_CONTEXT_MAX_CHARS", "12000").strip()
    try:
        return max(500, int(raw))
    except ValueError:
        return 12000


def tool_output_max_chars() -> int:
    raw = os.getenv("AQUILA_TOOL_OUTPUT_CHAR_CAP", "6000").strip()
    try:
        return max(500, int(raw))
    except ValueError:
        return 6000


def truncate_text(text: str, max_chars: int, *, suffix: str = "\n...[truncated]") -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def _read_gitignore_dirs(root: Path) -> set[str]:
    """Minimal .gitignore: directory names only (no full spec)."""
    ignore_path = root / ".gitignore"
    if not ignore_path.is_file():
        return set()
    dirs: set[str] = set()
    try:
        for line in ignore_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("/"):
                dirs.add(line.rstrip("/").split("/")[-1])
            elif "/" not in line and not line.startswith("*"):
                dirs.add(line)
    except OSError:
        pass
    return dirs


def _should_skip_dir_name(name: str, extra_ignore: set[str]) -> bool:
    return should_skip_dir(name) or name in extra_ignore


def _collect_key_files(root: Path, extra_ignore: set[str]) -> list[str]:
    found: list[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir_name(d, extra_ignore)]
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            if is_ignored_code_path(rel_dir):
                dirnames.clear()
                continue
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                rel = (Path(rel_dir) / fname).as_posix() if rel_dir != "." else fname
                if is_ignored_code_path(rel):
                    continue
                low = fname.lower()
                if (
                    fname.endswith(_KEY_EXTENSIONS)
                    or low.startswith("readme")
                    or "/tests/" in f"/{rel}/"
                    or rel.startswith("tests/")
                ):
                    found.append(rel)
                if len(found) >= _MAX_KEY_FILES:
                    return found
    except (OSError, ValueError):
        pass
    return found


def build_project_snapshot(root: Path, *, max_chars: int | None = None) -> str:
    """Shallow tree (depth 2) + key file paths, capped by max_chars."""
    cap = max_chars if max_chars is not None else snapshot_max_chars()
    if not root.is_dir():
        return ""

    extra_ignore = _read_gitignore_dirs(root)
    parts: list[str] = []

    tree = get_directory_tree(".", max_depth=2)
    if tree and not tree.startswith("❌"):
        parts.append("## Directory tree (depth 2)\n" + tree.strip())

    key_files = _collect_key_files(root.resolve(), extra_ignore)
    if key_files:
        parts.append("## Key files\n" + "\n".join(f"- {p}" for p in key_files))

    text = "\n\n".join(parts).strip()
    return truncate_text(text, cap)


def build_project_context_block() -> tuple[str, dict[str, Any]]:
    """Build PROJECT block text and snapshot metadata for metrics.extra."""
    meta: dict[str, Any] = {"snapshot_chars": 0, "snapshot_wall_ms": 0.0}
    started = time.monotonic()

    try:
        from tool_library.code_canvas_tools import get_active_project_scope

        scope = get_active_project_scope()
    except Exception:
        scope = None

    root = get_code_project_root()
    if scope:
        header = (
            f"Active code project: `{scope.get('project_name', 'project')}`\n"
            f"CODE_PROJECT_ROOT: {scope.get('root', '')}\n"
            "All file paths are relative to CODE_PROJECT_ROOT."
        )
    elif root:
        header = (
            f"Active code project: `{root.name}`\n"
            f"CODE_PROJECT_ROOT: {root}\n"
            "All file paths are relative to CODE_PROJECT_ROOT."
        )
    else:
        meta["snapshot_wall_ms"] = round((time.monotonic() - started) * 1000, 1)
        return (
            "No code project is active yet. Use write_file on a path under the project; "
            "parent directories are created automatically.",
            meta,
        )

    snapshot = ""
    if root and root.is_dir():
        snapshot = build_project_snapshot(root)

    meta["snapshot_chars"] = len(snapshot)
    meta["snapshot_wall_ms"] = round((time.monotonic() - started) * 1000, 1)

    if snapshot:
        return f"{header}\n\n{snapshot}", meta
    return header, meta


def parse_grep_hits(tool_out: str) -> list[tuple[str, int]]:
    """Parse grep_repo lines into (relative_path, line_number)."""
    hits: list[tuple[str, int]] = []
    for line in tool_out.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("OK") or line.startswith("ERROR"):
            continue
        if line.startswith("..."):
            continue
        m = _GREP_HIT_RE.match(line)
        if not m:
            continue
        rel, line_no, _content = m.group(1), int(m.group(2)), m.group(3)
        hits.append((rel.replace("\\", "/"), line_no))
    return hits


def maybe_auto_context_after_grep(tool_name: str, tool_out: str) -> str | None:
    """If enabled and grep returned 1-3 unique files, return a read_file snippet."""
    if tool_name != "grep" or not auto_context_enabled():
        return None
    if "ERROR" in tool_out[:20] or "No matches" in tool_out:
        return None

    hits = parse_grep_hits(tool_out)
    unique_files = list(dict.fromkeys(p for p, _ in hits))
    if not unique_files or len(unique_files) > 3:
        return None

    from agent.tool_library.code_agent_tools import read_file

    rel, line_no = hits[0]
    start = max(1, line_no - 10)
    end = line_no + 30
    snippet = read_file(rel, start, end)
    if snippet.startswith("❌"):
        return None

    block = f"Auto-context (from grep hit in `{rel}`):\n{snippet}"
    return truncate_text(block, auto_context_max_chars())
