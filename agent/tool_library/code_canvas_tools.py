"""
Code Canvas toolkit — structured project buffer (mirrors writing_tools pattern).
"""
import ast
import difflib
import inspect
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from language_registry import get_language, index_extensions, run_linter
from tools import is_ignored_code_path, normalize_workspace_path, read_file_lines, should_skip_dir

CODE_DIR = Path("Agent-Code")
CODE_DIR.mkdir(exist_ok=True)
ACTIVE_CODE_FILE = CODE_DIR / "active_code_state.json"
MAX_REGION_LINES = 150
MAX_NEW_FILE_LINES = 80
MAX_OUTLINE_FILES = 200
MAX_IMPORT_FILES = 5000


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", (name or "project").strip()).strip("_")
    return slug[:64] or "project"


def _project_root(state: dict) -> str:
    return normalize_workspace_path(state.get("root") or "Agent-Code")


def _relative_to_root(state: dict, path: str) -> str:
    """Store paths relative to project root (not workspace absolutes)."""
    p = normalize_workspace_path(path)
    root = _project_root(state)
    if p == root:
        return p
    prefix = root.rstrip("/") + "/"
    if p.startswith(prefix):
        return p[len(prefix) :]
    return p


def _disk_path(state: dict, path: str) -> Path:
    rel = _relative_to_root(state, path)
    return Path(_project_root(state)) / rel


def _load_state() -> dict:
    if not ACTIVE_CODE_FILE.exists():
        return {}
    with open(ACTIVE_CODE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(ACTIVE_CODE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _find_file(state: dict, path: str) -> dict | None:
    norm = _relative_to_root(state, path)
    for entry in state.get("files", []):
        if entry.get("path") == norm:
            return entry
    return None


def _ensure_file_content(state: dict, entry: dict) -> str:
    content = entry.get("content") or ""
    if content or not entry.get("indexed_only"):
        return content
    disk = _disk_path(state, entry["path"])
    if disk.is_file():
        try:
            content = disk.read_text(encoding="utf-8", errors="replace")
            entry["content"] = content
            entry["line_count"] = len(content.splitlines())
        except Exception:
            pass
    return entry.get("content") or ""


def _upsert_file(
    state: dict,
    path: str,
    content: str,
    dirty: bool = True,
    *,
    indexed_only: bool = False,
) -> dict:
    norm = _relative_to_root(state, path)
    spec = get_language(norm)
    lang = spec.name if spec else "unknown"
    entry = _find_file(state, norm)
    if entry:
        entry["content"] = content
        entry["line_count"] = len(content.splitlines()) if content else 0
        entry["language"] = lang
        entry["dirty"] = dirty
        if indexed_only:
            entry["indexed_only"] = True
    else:
        state.setdefault("files", []).append({
            "path": norm,
            "language": lang,
            "content": content,
            "line_count": len(content.splitlines()) if content else 0,
            "lint_status": "unknown",
            "last_test": "not_run",
            "dirty": dirty,
            "indexed_only": indexed_only,
        })
    return state


def _walk_source_files(root: Path, extensions: set[str]) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root)
            if is_ignored_code_path(str(rel.as_posix())):
                continue
            if name.endswith(tuple(extensions)):
                found.append(p)
            if len(found) >= MAX_IMPORT_FILES:
                return found
    return found


def _detect_dependency_hints(src: Path) -> dict:
    """Record venv + manifest paths without indexing site-packages."""
    hints: dict[str, str] = {}
    for vname in (".venv", "venv", "env"):
        vp = src / vname
        if vp.is_dir():
            hints["venv_dir"] = vname
            break
    if (src / "requirements.txt").is_file():
        hints["requirements_txt"] = "requirements.txt"
    if (src / "pyproject.toml").is_file():
        hints["pyproject_toml"] = "pyproject.toml"
    if (src / "package.json").is_file():
        hints["package_json"] = "package.json"
    return hints


def _prune_ignored_files(state: dict) -> int:
    files = state.get("files", [])
    kept = [f for f in files if not is_ignored_code_path(f.get("path", ""))]
    removed = len(files) - len(kept)
    state["files"] = kept
    return removed


def prune_ignored_buffer_files() -> str:
    """Remove .venv, node_modules, etc. from the code buffer manifest."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    removed = _prune_ignored_files(state)
    _save_state(state)
    if removed:
        return f"✅ Pruned {removed} ignored paths (venv/cache/build dirs) from buffer."
    return "✅ No ignored paths in buffer."


def _python_symbols(content: str) -> list[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names[:12]


def init_code_project(project_name: str, root: str = "", language_primary: str = "python") -> str:
    """Initialize the code canvas buffer. ALWAYS use this first in Code Mode."""
    slug = _slugify(project_name)
    norm_root = normalize_workspace_path(root) if root else ""
    if not norm_root or norm_root in (".", "./"):
        norm_root = f"Agent-Code/{slug}"
    elif norm_root.rstrip("/").endswith("Agent-Code"):
        norm_root = f"{norm_root.rstrip('/')}/{slug}"
    elif Path(norm_root).name != slug:
        norm_root = f"{norm_root.rstrip('/')}/{slug}"

    state = {
        "project_name": project_name,
        "root": norm_root,
        "language_primary": language_primary,
        "workspace_mode": "sandbox",
        "files": [],
        "test_targets": [],
        "notes": [],
    }
    _save_state(state)
    return (
        f"✅ Code project '{project_name}' initialized (primary: {language_primary}).\n"
        f"Disk root: {norm_root}/\n"
        "Use paths relative to this root only (e.g. tests/test_add.py, src/add.py). "
        "Call sync_project_to_disk before run_pytest."
    )


def import_codebase(
    source_path: str,
    project_name: str = "",
    workspace_mode: str = "sandbox",
    load_content: str = "false",
) -> str:
    """Import a directory manifest into the code buffer (sandbox copy or in-place)."""
    src = Path(normalize_workspace_path(source_path))
    if not src.is_dir():
        return f"❌ Error: '{source_path}' is not a directory."
    slug = _slugify(project_name or src.name)
    mode = (workspace_mode or "sandbox").lower()
    load_all = str(load_content).lower() in ("true", "1", "yes")

    if mode == "in_place":
        norm_root = normalize_workspace_path(str(src))
    else:
        norm_root = f"Agent-Code/{slug}"
        dest = Path(norm_root)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

    extensions = index_extensions()
    files = _walk_source_files(src, extensions)
    dep_hints = _detect_dependency_hints(src)
    state = {
        "project_name": project_name or src.name,
        "root": norm_root,
        "language_primary": "python",
        "workspace_mode": mode,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "dependency_hints": dep_hints,
        "files": [],
        "test_targets": [],
        "notes": [],
    }

    for fp in files:
        if mode == "sandbox":
            rel = fp.relative_to(src)
            target = Path(norm_root) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fp, target)
            buf_path = str(rel.as_posix())
            read_path = target
        else:
            rel = fp.relative_to(src)
            buf_path = str(rel.as_posix())
            read_path = fp

        content = ""
        if load_all and read_path.stat().st_size < 120_000:
            try:
                content = read_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
        line_count = len(content.splitlines()) if content else sum(
            1 for _ in open(read_path, encoding="utf-8", errors="replace")
        )
        spec = get_language(buf_path)
        state["files"].append({
            "path": buf_path,
            "language": spec.name if spec else "unknown",
            "content": content,
            "line_count": line_count,
            "lint_status": "unknown",
            "last_test": "not_run",
            "dirty": False,
            "indexed_only": not load_all,
        })

    removed = _prune_ignored_files(state)
    _save_state(state)
    msg = (
        f"✅ Imported {len(state['files'])} source files ({mode}) under {norm_root}/. "
        "Use read_code_outline or index_codebase_for_search; read_file_region for edits."
    )
    if dep_hints.get("venv_dir"):
        msg += (
            f"\n📦 Detected {dep_hints['venv_dir']}/ (not indexed). "
            "Use requirements.txt / imports for dependencies; pip install uses the active env."
        )
    if dep_hints.get("requirements_txt"):
        msg += f"\n📄 See {dep_hints['requirements_txt']} for Python dependencies."
    if removed:
        msg += f"\n(pruned {removed} paths under ignored dirs)"
    return msg


def attach_existing_repo(source_path: str, project_name: str = "") -> str:
    """Attach an existing repo in-place (no copy)."""
    return import_codebase(
        source_path,
        project_name,
        workspace_mode="in_place",
        load_content="false",
    )


def index_codebase_for_search(query: str, directory: str = "") -> str:
    """Semantic search scoped to the active project root."""
    from tool_library.coding_tools import semantic_code_search

    state = _load_state()
    root = directory.strip() or (_project_root(state) if state else ".")
    return semantic_code_search(query, root)


def read_code_outline() -> str:
    """List files in the buffer with line counts (low context cost)."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project. Use init_code_project first."
    mode = state.get("workspace_mode", "sandbox")
    lines = [
        f"PROJECT: {state.get('project_name', '?')} | root: {state.get('root', '.')} | mode: {mode}",
    ]
    files = [f for f in state.get("files", []) if not is_ignored_code_path(f.get("path", ""))]
    dep = state.get("dependency_hints", {})
    if dep.get("venv_dir"):
        lines.append(
            f"DEPS: {dep['venv_dir']}/ present (not indexed). "
            "Use requirements.txt / pyproject.toml + imports."
        )
    if not files:
        return lines[0] + "\n(no source files in buffer yet)"
    overflow = 0
    for i, f in enumerate(files):
        if i >= MAX_OUTLINE_FILES:
            overflow = len(files) - MAX_OUTLINE_FILES
            break
        dirty = " [dirty]" if f.get("dirty") else ""
        idx = " [indexed]" if f.get("indexed_only") else ""
        sym = ""
        if f.get("language") == "python":
            content = _ensure_file_content(state, f)
            if content:
                syms = _python_symbols(content)
                if syms:
                    sym = " | symbols: " + ", ".join(syms)
        lines.append(
            f"  - {f['path']} ({f.get('line_count', 0)} lines, "
            f"lint={f.get('lint_status', '?')}, test={f.get('last_test', '?')})"
            f"{dirty}{idx}{sym}"
        )
    if overflow:
        lines.append(f"  ... and {overflow} more files (use semantic_code_search to narrow)")
    targets = state.get("test_targets", [])
    if targets:
        lines.append("TEST TARGETS: " + ", ".join(targets))
    _save_state(state)
    return "\n".join(lines)


def read_file_region(file_path: str, start_line: int, end_line: int) -> str:
    """Read a line range from buffer or disk (max 150 lines)."""
    state = _load_state()
    norm = _relative_to_root(state, file_path)
    if end_line < start_line:
        start_line, end_line = end_line, start_line
    if end_line - start_line + 1 > MAX_REGION_LINES:
        end_line = start_line + MAX_REGION_LINES - 1
    entry = _find_file(state, norm) if state else None
    if entry:
        text = _ensure_file_content(state, entry)
        lines = text.splitlines()
        chunk = lines[start_line - 1 : end_line]
        return (
            f"--- {norm} lines {start_line}-{end_line} ---\n"
            + "\n".join(f"{i + start_line}: {l}" for i, l in enumerate(chunk))
        )
    return read_file_lines(norm, start_line, end_line)


def create_buffer_file(file_path: str, content: str) -> str:
    """Create a new file in the buffer (max ~80 lines recommended)."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project. Use init_code_project first."
    norm = _relative_to_root(state, file_path)
    if _find_file(state, norm):
        return f"❌ Error: '{norm}' exists. Use replace_lines or apply_unified_patch."
    line_count = len(content.splitlines())
    if line_count > MAX_NEW_FILE_LINES:
        return (
            f"❌ Error: New file has {line_count} lines (max {MAX_NEW_FILE_LINES}). "
            "Split into smaller chunks."
        )
    _upsert_file(state, norm, content)
    _save_state(state)
    return f"✅ Created buffer file '{norm}' ({line_count} lines)."


def replace_lines(file_path: str, start_line: int, end_line: int, new_content: str) -> str:
    """Replace an inclusive line range in a buffer file."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    norm = _relative_to_root(state, file_path)
    entry = _find_file(state, norm)
    if not entry:
        return f"❌ Error: '{norm}' not in buffer. Use create_buffer_file or read_code_outline."
    lines = entry["content"].splitlines(keepends=True)
    if not lines and entry["content"]:
        lines = [entry["content"]]
    start = max(1, start_line) - 1
    end = min(len(lines), end_line)
    new_lines = new_content.splitlines(keepends=True)
    if new_content and not new_content.endswith("\n") and new_lines:
        new_lines[-1] = new_lines[-1].rstrip("\n") + "\n"
    merged = lines[:start] + new_lines + lines[end:]
    new_text = "".join(merged)
    _upsert_file(state, norm, new_text)
    _save_state(state)
    return (
        f"✅ Replaced lines {start_line}-{end_line} in '{norm}' "
        f"(now {len(new_text.splitlines())} lines)."
    )


def apply_unified_patch(file_path: str, patch_text: str) -> str:
    """Apply a unified diff patch to one file in the buffer."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    norm = _relative_to_root(state, file_path)
    entry = _find_file(state, norm)
    if not entry:
        return f"❌ Error: '{norm}' not in buffer."
    if not patch_text.strip():
        return "❌ Error: Empty patch."

    try:
        new_text = _apply_patch_simple(entry["content"], patch_text)
    except Exception as e:
        return f"❌ Patch failed: {e}"

    _upsert_file(state, norm, new_text)
    _save_state(state)
    delta = len(new_text.splitlines()) - len(entry["content"].splitlines())
    return f"✅ Patched '{norm}' ({delta:+d} lines). Preview saved to buffer."


def _apply_patch_simple(original: str, patch_text: str) -> str:
    """Minimal unified-diff applier for single-file hunks."""
    orig_lines = original.splitlines()
    out_lines = orig_lines[:]
    hunk_old_start = None
    i = 0
    while i < len(patch_lines := patch_text.splitlines()):
        line = patch_lines[i]
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                hunk_old_start = int(m.group(1)) - 1
            i += 1
            continue
        if hunk_old_start is None:
            i += 1
            continue
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            idx = hunk_old_start
            if 0 <= idx < len(out_lines) and out_lines[idx] == line[1:]:
                out_lines.pop(idx)
            else:
                raise ValueError(f"Patch remove mismatch at line {idx + 1}")
            i += 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            out_lines.insert(hunk_old_start, line[1:])
            hunk_old_start += 1
            i += 1
            continue
        if line.startswith(" "):
            idx = hunk_old_start
            if 0 <= idx < len(out_lines):
                if out_lines[idx] != line[1:]:
                    raise ValueError(f"Context mismatch at line {idx + 1}")
                hunk_old_start += 1
            i += 1
            continue
        i += 1
    return "\n".join(out_lines) + ("\n" if original.endswith("\n") else "")


def replace_symbol(file_path: str, symbol_name: str, new_code: str) -> str:
    """Replace a Python def/class by name; other languages use line-heuristic fallback."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    norm = _relative_to_root(state, file_path)
    entry = _find_file(state, norm)
    if not entry:
        return f"❌ Error: '{norm}' not in buffer."
    spec = get_language(norm)
    content = entry["content"]
    lines = content.splitlines(keepends=True)

    if spec and spec.name == "python":
        start_idx = end_idx = -1
        for pattern in (f"def {symbol_name}(", f"class {symbol_name}("):
            for i, line in enumerate(lines):
                if line.strip().startswith(pattern):
                    start_idx = i
                    break
            if start_idx >= 0:
                break
        if start_idx < 0:
            return f"❌ Symbol '{symbol_name}' not found in '{norm}'."
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        end_idx = len(lines)
        for j in range(start_idx + 1, len(lines)):
            stripped = lines[j].lstrip()
            if stripped and not stripped.startswith("#"):
                indent = len(lines[j]) - len(lines[j].lstrip())
                if indent <= base_indent:
                    end_idx = j
                    break
        new_block = new_code if new_code.endswith("\n") else new_code + "\n"
        merged = lines[:start_idx] + [new_block] + lines[end_idx:]
        new_text = "".join(merged)
    else:
        return (
            f"❌ replace_symbol for {spec.name if spec else 'unknown'} not fully supported in v1. "
            "Use replace_lines on '{norm}'."
        )

    _upsert_file(state, norm, new_text)
    _save_state(state)
    return f"✅ Replaced symbol '{symbol_name}' in '{norm}'."


def delete_buffer_file(file_path: str, remove_from_disk: str = "false") -> str:
    """Remove a file from the buffer; optionally delete from disk."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    norm = _relative_to_root(state, file_path)
    files = state.get("files", [])
    new_files = [f for f in files if f.get("path") != norm]
    if len(new_files) == len(files):
        return f"❌ '{norm}' not in buffer."
    state["files"] = new_files
    _save_state(state)
    msg = f"✅ Removed '{norm}' from buffer."
    if str(remove_from_disk).lower() in ("true", "1", "yes"):
        p = Path(norm)
        if p.exists():
            p.unlink()
            msg += " Deleted from disk."
    return msg


def set_test_targets(targets: str) -> str:
    """Comma-separated pytest paths relative to project root, e.g. 'tests/test_foo.py'."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    state["test_targets"] = [
        _relative_to_root(state, t.strip()) for t in targets.split(",") if t.strip()
    ]
    _save_state(state)
    return f"✅ Test targets: {state['test_targets']}"


def sync_project_to_disk() -> str:
    """Write all buffer files under project root to disk and run linters."""
    state = _load_state()
    if not state:
        return "❌ Error: No active code project."
    written = []
    root = _project_root(state)
    Path(root).mkdir(parents=True, exist_ok=True)
    for entry in state.get("files", []):
        if entry.get("indexed_only") and not entry.get("dirty") and not entry.get("content"):
            continue
        disk = _disk_path(state, entry["path"])
        disk.parent.mkdir(parents=True, exist_ok=True)
        content = _ensure_file_content(state, entry)
        disk.write_text(content, encoding="utf-8")
        entry["dirty"] = False
        lint = run_linter(str(disk), entry["content"])
        entry["lint_status"] = lint.status
        written.append(f"{disk.as_posix()} (lint={lint.status})")
    _save_state(state)
    if not written:
        return "⚠️ No files to sync."
    return "✅ Synced to disk:\n" + "\n".join(f"  - {w}" for w in written)


def _pytest_path_args(state: dict, target: str) -> str:
    if target.strip():
        rels = [t.strip() for t in target.split() if t.strip()]
    else:
        rels = state.get("test_targets", []) if state else []
    if not rels:
        root = _project_root(state) if state else "."
        return root
    disks = [_disk_path(state, r) for r in rels]
    return " ".join(d.as_posix() for d in disks)


def run_pytest(target: str = "") -> str:
    """Run pytest on target path or project test_targets (syncs dirty files first)."""
    from language_registry import run_tests

    state = _load_state()
    if not state:
        return "❌ Error: No active code project. Use init_code_project first."
    if any(f.get("dirty") for f in state.get("files", [])):
        sync_project_to_disk()
        state = _load_state()
    paths = _pytest_path_args(state, target)
    cwd = os.getcwd()
    result = run_tests(paths)
    status = "passed" if result.ok else "failed"
    if state:
        for entry in state.get("files", []):
            if entry["path"].endswith(".py"):
                entry["last_test"] = status
        _save_state(state)
    icon = "✅" if result.ok else "❌"
    hint = ""
    if "not found" in result.summary.lower() or "no tests ran" in result.summary.lower():
        hint = (
            f"\nHint: project root is {_project_root(state)}/; "
            "use paths like tests/test_add.py, then sync_project_to_disk."
        )
    return (
        f"{icon} pytest (cwd={cwd}): {result.passed} passed, {result.failed} failed\n"
        f"targets: {paths}\n"
        f"{result.summary[:1500]}{hint}"
    )


def run_linter_tool(file_path: str) -> str:
    """Run linter for file's language via language_registry."""
    state = _load_state()
    norm = _relative_to_root(state, file_path) if state else normalize_workspace_path(file_path)
    content = None
    entry = _find_file(state, norm) if state else None
    if entry:
        content = entry["content"]
    result = run_linter(norm, content)
    if entry:
        entry["lint_status"] = result.status
        _save_state(state)
    icon = "✅" if result.ok else "⚠️"
    line = f" line {result.line}" if result.line else ""
    return f"{icon} {norm}: {result.status}{line} — {result.message}"


CODE_CANVAS_TOOLS = {
    "init_code_project": {"func": init_code_project, "description": inspect.getdoc(init_code_project)},
    "read_code_outline": {"func": read_code_outline, "description": inspect.getdoc(read_code_outline)},
    "read_file_region": {"func": read_file_region, "description": inspect.getdoc(read_file_region)},
    "create_buffer_file": {"func": create_buffer_file, "description": inspect.getdoc(create_buffer_file)},
    "replace_lines": {"func": replace_lines, "description": inspect.getdoc(replace_lines)},
    "apply_unified_patch": {"func": apply_unified_patch, "description": inspect.getdoc(apply_unified_patch)},
    "replace_symbol": {"func": replace_symbol, "description": inspect.getdoc(replace_symbol)},
    "delete_buffer_file": {"func": delete_buffer_file, "description": inspect.getdoc(delete_buffer_file)},
    "set_test_targets": {"func": set_test_targets, "description": inspect.getdoc(set_test_targets)},
    "sync_project_to_disk": {"func": sync_project_to_disk, "description": inspect.getdoc(sync_project_to_disk)},
    "run_pytest": {"func": run_pytest, "description": inspect.getdoc(run_pytest)},
    "run_linter": {"func": run_linter_tool, "description": inspect.getdoc(run_linter_tool)},
    "import_codebase": {"func": import_codebase, "description": inspect.getdoc(import_codebase)},
    "attach_existing_repo": {
        "func": attach_existing_repo,
        "description": inspect.getdoc(attach_existing_repo),
    },
    "index_codebase_for_search": {
        "func": index_codebase_for_search,
        "description": inspect.getdoc(index_codebase_for_search),
    },
    "prune_ignored_buffer_files": {
        "func": prune_ignored_buffer_files,
        "description": inspect.getdoc(prune_ignored_buffer_files),
    },
}
