"""Light coding for Chat Mode: repo walk, budgeted file reads, overflow summaries."""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .language_registry import get_language, index_extensions
from agent.core.tools import is_ignored_code_path, normalize_workspace_path, should_skip_dir

_TIER0_NAMES = frozenset({
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "main.py",
    "app.py",
    "__main__.py",
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
})

_QUOTED_ID_RE = re.compile(r"""['"]([\w.]+)['"]""")
_CAMEL_RE = re.compile(r"\b([A-Z][a-zA-Z0-9_]{2,})\b")


@dataclass(frozen=True)
class LightCodingConfig:
    token_budget: int = 20000
    max_files_full: int = 40
    file_char_cap: int = 12000
    max_walk_files: int = 2000
    grep_max: int = 30


def load_light_coding_config() -> LightCodingConfig:
    def _int(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return max(1, int(raw))
        except ValueError:
            return default

    return LightCodingConfig(
        token_budget=_int("AQUILA_LIGHT_CODING_TOKEN_BUDGET", 20000),
        max_files_full=_int("AQUILA_LIGHT_CODING_MAX_FILES_FULL", 40),
        file_char_cap=_int("AQUILA_LIGHT_CODING_FILE_CHAR_CAP", 12000),
        max_walk_files=_int("AQUILA_LIGHT_CODING_MAX_WALK_FILES", 2000),
        grep_max=_int("AQUILA_LIGHT_CODING_GREP_MAX", 30),
    )


@dataclass
class LightCodingSessionCache:
    repo_root: str = ""
    block: str = ""
    stats: dict | None = None


_session_cache = LightCodingSessionCache()


def get_session_cache() -> LightCodingSessionCache:
    return _session_cache


def invalidate_session_cache() -> None:
    _session_cache.repo_root = ""
    _session_cache.block = ""
    _session_cache.stats = None


def _estimate_tokens(text: str) -> int:
    return max(0, len(text or "") // 4)


def _resolve_repo_root(repo_root: str) -> Path | None:
    raw = (repo_root or "").strip()
    if not raw:
        return None
    norm = normalize_workspace_path(raw)
    root = Path(norm)
    if not root.is_absolute():
        root = Path(os.path.abspath(norm))
    try:
        root = root.resolve()
    except OSError:
        return None
    if not root.is_dir():
        return None
    return root


def _is_walk_candidate(name: str, extensions: set[str]) -> bool:
    lower = name.lower()
    if lower.startswith("readme") or lower.startswith("architecture"):
        return True
    if lower in _TIER0_NAMES:
        return True
    ext_tuple = tuple(extensions)
    return bool(ext_tuple) and name.endswith(ext_tuple)


def _walk_source_files(root: Path, extensions: set[str], max_files: int) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root)
            if is_ignored_code_path(str(rel.as_posix())):
                continue
            if not _is_walk_candidate(name, extensions):
                continue
            found.append(p)
            if len(found) >= max_files:
                return found
    return found


def _user_path_tokens(user_input: str) -> set[str]:
    tokens: set[str] = set()
    for word in re.split(r"[^\w./-]+", (user_input or "").lower()):
        word = word.strip("./")
        if len(word) >= 3:
            tokens.add(word)
    return tokens


def _tier0_match(rel_path: str) -> bool:
    name = Path(rel_path).name
    lower = name.lower()
    if lower.startswith("readme") or lower.startswith("architecture"):
        return True
    return lower in _TIER0_NAMES


def _file_tier(rel_path: str, user_tokens: set[str], grep_hits: set[str]) -> tuple[int, int, str]:
    rel_norm = rel_path.replace("\\", "/")
    if _tier0_match(rel_norm):
        return (0, rel_norm.count("/"), rel_norm.lower())
    if rel_norm in grep_hits or any(h in rel_norm for h in grep_hits):
        return (2, rel_norm.count("/"), rel_norm.lower())
    rel_lower = rel_norm.lower()
    if user_tokens and any(t in rel_lower for t in user_tokens):
        return (1, rel_norm.count("/"), rel_lower)
    return (3, rel_norm.count("/"), rel_lower)


def _grep_hit_paths(root: Path, user_input: str, *, max_matches: int) -> set[str]:
    patterns: list[str] = []
    seen_pat: set[str] = set()
    for match in _QUOTED_ID_RE.finditer(user_input or ""):
        pat = match.group(1).strip()
        if pat and pat not in seen_pat:
            seen_pat.add(pat)
            patterns.append(pat)
    for match in _CAMEL_RE.finditer(user_input or ""):
        pat = match.group(1).strip()
        if pat and pat not in seen_pat:
            seen_pat.add(pat)
            patterns.append(pat)

    hits: set[str] = set()
    if not patterns:
        return hits

    from tool_library.grep_tools import grep_repo

    for pat in patterns[:8]:
        try:
            result = grep_repo(pat, path=str(root), max_matches=max_matches)
        except Exception:
            continue
        for line in result.splitlines()[1:]:
            if ":" not in line:
                continue
            path_part = line.split(":", 1)[0].strip()
            if path_part:
                hits.add(path_part.replace("\\", "/"))
    return hits


def _python_symbols(content: str) -> list[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names[:8]


def _read_file_capped(path: Path, char_cap: int) -> tuple[str, int, bool]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", 0, False
    line_count = len(text.splitlines()) if text else 0
    truncated = len(text) > char_cap
    if truncated:
        text = text[:char_cap] + f"\n... [truncated at {char_cap} chars]"
    return text, line_count, truncated


def _compact_summary(rel_path: str, content: str, line_count: int) -> str:
    lang = get_language(rel_path)
    lang_name = lang.name if lang else "unknown"
    preview = (content or "").replace("\n", " ").strip()[:200]
    sym_part = ""
    if lang and lang.name == "python" and content:
        syms = _python_symbols(content)
        if syms:
            sym_part = f" | symbols: {', '.join(syms)}"
    prev_part = f' | preview: "{preview}"' if preview else ""
    return f"  - {rel_path} ({line_count} lines, {lang_name}){sym_part}{prev_part}"


def build_light_coding_context(
    repo_root: str,
    user_input: str = "",
    *,
    config: LightCodingConfig | None = None,
    force_refresh: bool = False,
) -> tuple[str, dict]:
    """Walk repo, rank files, fill token budget with reads + overflow summaries."""
    config = config or load_light_coding_config()
    root = _resolve_repo_root(repo_root)
    stats: dict = {
        "repo_root": repo_root,
        "files_walked": 0,
        "files_full": 0,
        "files_summary": 0,
        "tokens_used": 0,
        "token_budget": config.token_budget,
        "error": "",
    }

    if root is None:
        stats["error"] = f"Repo path not found: {repo_root}"
        return "", stats

    root_str = str(root)
    if (
        not force_refresh
        and _session_cache.repo_root == root_str
        and _session_cache.block
    ):
        stats.update(_session_cache.stats or {})
        stats["cached"] = True
        return _session_cache.block, stats

    extensions = index_extensions()
    all_files = _walk_source_files(root, extensions, config.max_walk_files)
    stats["files_walked"] = len(all_files)

    user_tokens = _user_path_tokens(user_input)
    grep_hits = _grep_hit_paths(root, user_input, max_matches=config.grep_max)

    ranked: list[tuple[tuple[int, int, str], Path]] = []
    for path in all_files:
        rel = path.relative_to(root).as_posix()
        tier_key = _file_tier(rel, user_tokens, grep_hits)
        ranked.append((tier_key, path))
    ranked.sort(key=lambda item: item[0])

    char_budget = config.token_budget * 4
    used_chars = 0
    full_blocks: list[str] = []
    summary_lines: list[str] = []
    full_paths: set[str] = set()
    files_full = 0

    header = (
        f"# Light code context\n"
        f"Project root: `{root}`\n"
        f"Files indexed: {len(all_files)} (walk cap {config.max_walk_files})\n"
        f"Token budget: ~{config.token_budget}\n"
        f"This is a partial snapshot — not every file is included in full.\n"
    )
    used_chars += len(header)

    for _tier_key, path in ranked:
        rel = path.relative_to(root).as_posix()
        if files_full >= config.max_files_full:
            break
        content, line_count, _trunc = _read_file_capped(path, config.file_char_cap)
        if not content and line_count == 0:
            continue
        block = f"--- FILE: {rel} ---\n{content}\n--- END FILE ---"
        if used_chars + len(block) > char_budget:
            break
        full_blocks.append(block)
        full_paths.add(rel)
        used_chars += len(block)
        files_full += 1

    for _tier_key, path in ranked:
        rel = path.relative_to(root).as_posix()
        if rel in full_paths:
            continue
        content, line_count, _ = _read_file_capped(path, 400)
        summary_lines.append(_compact_summary(rel, content, line_count))

    overflow_header = "\n## Remaining files (summaries only)\n"
    if summary_lines:
        overflow_block = overflow_header + "\n".join(summary_lines)
    else:
        overflow_block = ""

    body_parts = [header.strip()]
    if full_blocks:
        body_parts.append("\n\n".join(full_blocks))
    if overflow_block and used_chars + len(overflow_block) <= char_budget:
        body_parts.append(overflow_block.strip())
        used_chars += len(overflow_block)
    elif overflow_block:
        remaining = char_budget - used_chars - len(overflow_header) - 80
        if remaining > 200:
            trimmed = summary_lines[: max(1, remaining // 120)]
            body_parts.append(
                overflow_header.strip()
                + "\n"
                + "\n".join(trimmed)
                + f"\n  ... and {len(summary_lines) - len(trimmed)} more files"
            )

    block = "\n\n".join(body_parts).strip()
    char_budget = config.token_budget * 4
    if len(block) > char_budget:
        block = block[:char_budget] + "\n... [context truncated to token budget]"
    stats["files_full"] = files_full
    stats["files_summary"] = len(summary_lines)
    stats["tokens_used"] = _estimate_tokens(block)
    stats["cached"] = False

    _session_cache.repo_root = root_str
    _session_cache.block = block
    _session_cache.stats = dict(stats)

    return block, stats
