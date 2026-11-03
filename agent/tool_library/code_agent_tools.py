"""Direct filesystem tools for Phase 1 code agent loop."""
from __future__ import annotations

import fnmatch
import inspect
import os
from pathlib import Path

from agent.core.tools import get_directory_tree
from agent.core import (
    get_code_project_root,
    is_safe_path,
    resolve_tool_path,
    should_skip_dir,
)
from agent.tool_library.grep_tools import grep_repo
from agent.tool_library.run_tools import run_command


def _max_write_chars() -> int:
    raw = os.getenv("AQUILA_CODE_MAX_WRITE_CHARS", "8000").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 8000


def _require_project_root() -> Path | str:
    root = get_code_project_root()
    if not root:
        return (
            "❌ OS BLOCK: No code project is open. "
            "The harness or GUI should initialize a project under Agent-Code/ first."
        )
    return root


def read_file(
    path: str,
    start_line: int = 1,
    end_line: int = 0,
) -> str:
    """Read a file with line numbers. Paths are relative to CODE_PROJECT_ROOT."""
    block = _require_project_root()
    if isinstance(block, str):
        return block

    try:
        start = max(1, int(start_line))
    except (TypeError, ValueError):
        start = 1
    try:
        end = int(end_line) if end_line else 0
    except (TypeError, ValueError):
        end = 0

    target = resolve_tool_path(path)
    if not is_safe_path(target):
        return f"❌ SECURITY BLOCK: Cannot read '{path}'."
    if not target.is_file():
        return f"❌ Error: File not found: {path}"

    if end <= 0:
        try:
            with target.open(encoding="utf-8", errors="replace") as fh:
                all_lines = fh.readlines()
        except OSError as exc:
            return f"❌ Error reading file: {exc}"
        total = len(all_lines)
        end = min(total, start + 199) if total else start

    try:
        with target.open(encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
    except OSError as exc:
        return f"❌ Error reading file: {exc}"

    total = len(all_lines)
    if start > total:
        return f"❌ Error: start_line {start} exceeds file length ({total})."
    end = min(total, max(start, end))
    slice_lines = all_lines[start - 1 : end]
    numbered = "\n".join(f"{start + i}|{line.rstrip()}" for i, line in enumerate(slice_lines))
    return f"✅ {path} (lines {start}-{end})\n{numbered}"


def write_file(path: str, content: str) -> str:
    """Create or overwrite a file under CODE_PROJECT_ROOT."""
    block = _require_project_root()
    if isinstance(block, str):
        return block

    if content is None:
        return "❌ OS BLOCK: write_file requires content."
    text = str(content)
    max_chars = _max_write_chars()
    if len(text) > max_chars:
        return (
            f"❌ OS BLOCK: write_file content is {len(text)} chars (max {max_chars}). "
            "Use search_replace for edits to existing files, or split into smaller files."
        )

    target = resolve_tool_path(path, for_write=True)
    root = block.resolve()
    try:
        target.resolve().relative_to(root)
    except ValueError:
        return (
            f"❌ CODE MODE: Cannot write outside the open project ({root}). "
            f"Rejected path: {path}"
        )
    if not is_safe_path(target):
        return f"❌ SECURITY BLOCK: Cannot write '{path}'."

    # Direct disk write (no core_write_file flake8/SYSTEM HINT — those name replace_in_file).
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not text.endswith("\n") and target.suffix == ".py":
            text = text + "\n"
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"❌ Error writing file: {exc}"

    if target.suffix == ".py":
        import ast

        try:
            ast.parse(text)
        except SyntaxError as e:
            return (
                f"✅ Wrote {path}, but Python syntax error: {e.msg} "
                f"(line {e.lineno}). Use search_replace to fix."
            )
    return f"✅ Successfully wrote {path}."


def search_replace(path: str, old_string: str, new_string: str) -> str:
    """Replace exactly one occurrence of old_string in path."""
    block = _require_project_root()
    if isinstance(block, str):
        return block

    if not old_string:
        return "❌ OS BLOCK: old_string is required and must be non-empty."

    target = resolve_tool_path(path, for_write=True)
    root = block.resolve()
    try:
        target.resolve().relative_to(root)
    except ValueError:
        return f"❌ CODE MODE: Cannot edit outside the open project. Rejected: {path}"
    if not is_safe_path(target):
        return f"❌ SECURITY BLOCK: Cannot edit '{path}'."
    if not target.is_file():
        return f"❌ Error: File not found: {path}"

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"❌ Error reading file: {exc}"

    count = content.count(old_string)
    if count == 0:
        preview = content[:400].replace("\n", "\\n")
        return (
            f"❌ Error: old_string not found in {path}. "
            f"No replacement made. File starts with: {preview!r}"
        )
    if count > 1:
        return (
            f"❌ Error: old_string matched {count} times in {path}. "
            "Include more surrounding context so the match is unique."
        )

    new_content = content.replace(old_string, new_string, 1)
    try:
        target.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return f"❌ Error writing file: {exc}"

    rel = path
    try:
        rel = str(target.relative_to(root))
    except ValueError:
        pass
    return f"✅ Replaced text in {rel}."


def list_dir(path: str = ".", max_depth: int = 2) -> str:
    """List directory tree under CODE_PROJECT_ROOT."""
    block = _require_project_root()
    if isinstance(block, str):
        return block
    try:
        depth = max(1, min(5, int(max_depth)))
    except (TypeError, ValueError):
        depth = 2
    return get_directory_tree(path or ".", max_depth=depth)


def grep(pattern: str, path: str = ".", glob: str = "*") -> str:
    """Search file contents under path for pattern."""
    block = _require_project_root()
    if isinstance(block, str):
        return block
    return grep_repo(pattern, path or ".", glob or "*")


def find_files(glob_pattern: str, path: str = ".") -> str:
    """Glob filenames under project root (e.g. '**/test_*.py')."""
    block = _require_project_root()
    if isinstance(block, str):
        return block

    pattern = (glob_pattern or "*").strip()
    if not pattern:
        return "❌ Error: glob_pattern is required."

    target = resolve_tool_path(path or ".")
    if not is_safe_path(target):
        return f"❌ SECURITY BLOCK: Cannot search '{path}'."
    if not target.exists():
        return f"❌ Error: Path not found: {path}"

    matches: list[str] = []
    project_root = block.resolve()

    def _add_match(fpath: Path) -> bool:
        if not fpath.is_file() or not is_safe_path(fpath):
            return False
        try:
            rel = fpath.resolve().relative_to(project_root)
            matches.append(str(rel).replace("\\", "/"))
        except ValueError:
            matches.append(str(fpath))
        return len(matches) >= 50

    if "**" in pattern:
        base = target if target.is_dir() else target.parent
        for fpath in base.glob(pattern):
            if _add_match(fpath):
                break
    else:
        for root, dirs, filenames in os.walk(target):
            dirs[:] = [d for d in dirs if not should_skip_dir(d)]
            for fname in filenames:
                if fnmatch.fnmatch(fname, pattern):
                    if _add_match(Path(root) / fname):
                        break
            if len(matches) >= 50:
                break

    if not matches:
        return f"No files matching '{pattern}' under {path}"
    body = "\n".join(matches)
    if len(matches) >= 50:
        body += "\n... capped at 50 matches"
    return f"Found {len(matches)} match(es) for '{pattern}':\n{body}"


def semantic_search(query: str) -> str:
    """Query Chroma over active code project (lazy index)."""
    block = _require_project_root()
    if isinstance(block, str):
        return block
    q = (query or "").strip()
    if not q:
        return "❌ Error: query is required."
    from agent.tool_library.coding_tools import semantic_code_search

    return semantic_code_search(q)


CODE_AGENT_TOOL_REGISTRY: dict[str, dict] = {
    "read_file": {"func": read_file, "description": inspect.getdoc(read_file) or ""},
    "write_file": {"func": write_file, "description": inspect.getdoc(write_file) or ""},
    "search_replace": {
        "func": search_replace,
        "description": inspect.getdoc(search_replace) or "",
    },
    "list_dir": {"func": list_dir, "description": inspect.getdoc(list_dir) or ""},
    "grep": {"func": grep, "description": inspect.getdoc(grep) or ""},
    "find_files": {"func": find_files, "description": inspect.getdoc(find_files) or ""},
    "semantic_search": {
        "func": semantic_search,
        "description": inspect.getdoc(semantic_search) or "",
    },
    "run_command": {"func": run_command, "description": inspect.getdoc(run_command) or ""},
}
