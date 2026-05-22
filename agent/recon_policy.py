"""Code-mode recon tool pinning, playbooks, and documentation-task detection."""
from __future__ import annotations

import re

CODE_RECON_PINNED = frozenset({
    "get_directory_tree",
    "read_code_outline",
    "search_files",
})

CODE_DOC_PINNED = frozenset({
    "write_project_markdown",
})

DOC_TASK_KEYWORDS = (
    "architecture.md",
    "readme.md",
    "documentation",
    "document ",
    "write me a",
    "writemea",
    "write an ",
    "write the ",
)

RECON_PLAYBOOK_MARKDOWN = """## OS recon playbook (Code Mode)
1. Map layout → `get_directory_tree(path=".", max_depth=2)` ONCE on CODE_PROJECT_ROOT
2. File manifest → `read_code_outline()` once before deep reads
3. Find a filename → `search_files` with relative path only (never absolute Windows paths)
4. Read code → `read_file_region` for line ranges; avoid huge `read_file` on large files
5. NEVER: more than 2 `list_directory` calls per step — use the tree instead
6. Doc deliverable (ARCHITECTURE.md / README) → `write_project_markdown` after recon, not endless notes
"""

# Rich routing blurbs merged into Chroma index (see memory.index_tools)
TOOL_ROUTING_BLURBS: dict[str, str] = {
    "get_directory_tree": (
        "USE WHEN: first layout recon of a repo; one call replaces many list_directory calls. "
        "Prefer max_depth=2 on project root. Do NOT use on parent agent-projects folder."
    ),
    "list_directory": (
        "USE WHEN: inspect one known folder after tree/outline. "
        "Do NOT use repeatedly to map the repo — use get_directory_tree instead."
    ),
    "read_code_outline": (
        "USE WHEN: Code Mode project attached; call once per project before deep file reads. "
        "Returns buffer manifest and symbols."
    ),
    "search_files": (
        "USE WHEN: find files by glob pattern under project root. "
        "Use relative path '.' only; never absolute or doubled Agent-Code paths."
    ),
    "write_project_markdown": (
        "USE WHEN: ARCHITECTURE.md, README.md, or other repo documentation in Code Mode. "
        "Not write_file."
    ),
}


def is_documentation_task(*texts: str) -> bool:
    combined = " ".join(t for t in texts if t).lower()
    return any(kw in combined for kw in DOC_TASK_KEYWORDS)


def pinned_tools_for_code_step(
    step_kind: str,
    *,
    objective: str = "",
    user_request: str = "",
) -> frozenset[str]:
    """Tools always included in routed schema for this code-mode step."""
    pinned: set[str] = set()
    if step_kind in ("explore", "read"):
        pinned |= set(CODE_RECON_PINNED)
    if step_kind in ("code", "finalize", "write") and is_documentation_task(
        objective, user_request
    ):
        pinned |= set(CODE_DOC_PINNED)
    return frozenset(pinned)


def code_explore_hint() -> str:
    return (
        "Recon: get_directory_tree(max_depth=2) on CODE_PROJECT_ROOT, then read_code_outline. "
        "Max 2 list_directory per step. Use write_project_markdown for ARCHITECTURE.md/README."
    )


def expand_code_documentation_plan(
    plan: dict,
    user_request: str,
) -> tuple[dict, str]:
    """Replace over-long explore-heavy plans with a short doc-writing template."""
    steps = plan.get("steps") or []
    if not is_documentation_task(user_request):
        return plan, ""

    explore_count = sum(
        1 for s in steps if isinstance(s, dict) and s.get("step_kind") == "explore"
    )
    if len(steps) <= 5 and explore_count <= 1:
        return plan, ""

    req = (user_request or "documentation").strip()[:400]
    template = [
        (
            "explore",
            f"get_directory_tree + read_code_outline for: {req}",
        ),
        (
            "read",
            "Read key entrypoints (main, config, package manifests) via read_file_region.",
        ),
        (
            "code",
            f"write_project_markdown for deliverable: {req}",
        ),
        (
            "finalize",
            "sync_project_to_disk if needed; finish_task with brief summary.",
        ),
    ]
    from plan_validator import BUDGET_RUBRIC

    new_steps = []
    for kind, desc in template:
        _, default, _ = BUDGET_RUBRIC.get(kind, (3, 4, 6))
        new_steps.append({
            "status": "pending",
            "description": desc,
            "step_kind": kind,
            "max_iterations": default,
        })
    plan["steps"] = new_steps
    return plan, (
        f"Replaced {len(steps)}-step plan with {len(new_steps)}-step documentation template "
        f"(was {explore_count} explore steps)."
    )


def routing_document_for_tool(name: str, description: str) -> str:
    blurb = TOOL_ROUTING_BLURBS.get(name)
    base = (description or "").strip().split("\n")[0]
    if blurb:
        return f"Tool Name: {name}. {blurb} Original: {base}"
    return f"Tool Name: {name}. Description: {base}"


def normalize_code_tool_path(path: str) -> tuple[str, str | None]:
    """
    Fix absolute or doubled Agent-Code prefixes before directory/search tools run.
    Returns (normalized_path, warning_or_none).
    """
    raw = (path or ".").strip()
    if not raw:
        return ".", None

    note_parts: list[str] = []
    cleaned = raw.replace("\\", "/")

    if re.match(r"^[a-zA-Z]:/", cleaned):
        parts = [p for p in cleaned.split("/") if p]
        for i, part in enumerate(parts):
            if part.lower() == "agent-code" and i + 1 < len(parts):
                cleaned = "/".join(parts[i + 1 :])
                note_parts.append("stripped absolute path to project-relative")
                break
        else:
            cleaned = parts[-1] if parts else "."
            note_parts.append("stripped to basename from absolute path")

    marker = "agent-code/"
    if cleaned.lower().count(marker) >= 2:
        idx = cleaned.lower().rfind(marker)
        cleaned = cleaned[idx + len(marker) :]
        note_parts.append("removed duplicated Agent-Code/ prefix")

    if not cleaned or cleaned in (".", "/"):
        cleaned = "."
    if cleaned.startswith("/"):
        cleaned = cleaned.lstrip("/")

    note = "; ".join(note_parts) if note_parts else None
    return cleaned, note


def normalize_search_files_path(path: str) -> tuple[str, str | None]:
    """Alias for normalize_code_tool_path (search_files)."""
    return normalize_code_tool_path(path)


def normalize_directory_tool_path(path: str) -> tuple[str, str | None]:
    """Alias for normalize_code_tool_path (get_directory_tree, list_directory)."""
    return normalize_code_tool_path(path)
