"""Source of truth for tool metadata, aliases, and mode/step routing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Canonical name -> deprecated alias still accepted by executor
TOOL_ALIASES: dict[str, str] = {
    "search_files": "grep_repo",
    "search_in_file": "grep_repo",
    "apply_unified_patch": "apply_patch",
    "replace_function": "replace_symbol",
}

INTERNAL_TOOL_NAMES = frozenset({"_index_codebase"})

ALL_MODES = frozenset({"task", "code", "research", "writing", "autonomous", "character_build"})

STEP_KINDS_ALL = frozenset({
    "explore", "search", "read", "code", "verify", "synthesize", "write",
    "finalize", "tdd_red", "tdd_green", "tdd_refactor",
})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    family: str
    summary: str
    use_when: str
    do_not_use: str
    modes: frozenset[str]
    step_kinds: frozenset[str] | None  # None = all kinds allowed in mode filter
    required_in_modes: frozenset[str] = frozenset()
    deprecated_alias_of: str | None = None
    max_result_chars: int | None = None


def _spec(
    name: str,
    family: str,
    summary: str,
    use_when: str = "",
    do_not_use: str = "",
    modes: frozenset[str] | None = None,
    step_kinds: frozenset[str] | None = None,
    required_in_modes: frozenset[str] = frozenset(),
    deprecated_alias_of: str | None = None,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        family=family,
        summary=summary,
        use_when=use_when or summary,
        do_not_use=do_not_use,
        modes=modes or ALL_MODES,
        step_kinds=step_kinds,
        required_in_modes=required_in_modes,
        deprecated_alias_of=deprecated_alias_of,
    )


# Overrides and explicit specs (merged with runtime tool dict)
TOOL_SPECS: dict[str, ToolSpec] = {
    "grep_repo": _spec(
        "grep_repo", "search",
        "Search file contents under a path",
        "Find text or symbols across the repo",
        "Do not use for directory layout — use get_directory_tree",
        modes=frozenset({"task", "code", "research", "autonomous"}),
    ),
    "read_file_smart": _spec(
        "read_file_smart", "read",
        "Read file with automatic line cap",
        "Quick read of small/medium files",
        "Large files — use read_file_region",
    ),
    "get_directory_tree": _spec(
        "get_directory_tree", "read",
        "Directory tree layout",
        "First recon of repo root",
        "Repeated list_directory calls",
        modes=frozenset({"task", "code", "research", "autonomous"}),
    ),
    "read_code_outline": _spec(
        "read_code_outline", "read",
        "Code project manifest",
        "Once per code step before deep reads",
        modes=frozenset({"code", "task", "autonomous"}),
    ),
    "write_project_markdown": _spec(
        "write_project_markdown", "deliver",
        "Write ARCHITECTURE.md / README in code project",
        "Documentation deliverable in code mode",
        "Not write_file",
        modes=frozenset({"code"}),
        required_in_modes=frozenset({"code"}),
    ),
    "append_project_markdown": _spec(
        "append_project_markdown", "deliver",
        "Append sections to ARCHITECTURE.md / README",
        "After write_project_markdown; max ~4k chars per call",
        modes=frozenset({"code"}),
    ),
    "apply_patch": _spec(
        "apply_patch", "edit",
        "Apply unified diff",
        deprecated_alias_of="apply_unified_patch",
        modes=frozenset({"code"}),
    ),
    "run_command": _spec(
        "run_command", "run",
        "Allowlisted shell command in project cwd",
        modes=frozenset({"task", "code", "autonomous"}),
    ),
    "git_status": _spec("git_status", "run", "Git status", modes=frozenset({"code"})),
    "git_diff": _spec("git_diff", "run", "Git diff", modes=frozenset({"code"})),
    "checkpoint_step": _spec("checkpoint_step", "memory", "Save step checkpoint", modes=ALL_MODES),
    "save_task_deliverable": _spec("save_task_deliverable", "deliver", "Save Agent-Creations/Research file", modes=ALL_MODES),
    "mark_objective_complete": _spec("mark_objective_complete", "meta", "Complete current plan step", modes=ALL_MODES),
    "finish_task": _spec("finish_task", "meta", "End entire task", modes=ALL_MODES),
    "web_search": _spec(
        "web_search", "web", "Web search",
        modes=frozenset({"research", "task", "autonomous", "character_build"}),
    ),
    "read_webpage": _spec(
        "read_webpage", "web", "Fetch URL",
        modes=frozenset({"research", "task", "autonomous", "character_build"}),
    ),
    "write_persona_file": _spec(
        "write_persona_file", "persona",
        "Write initialization.md or notes under persona build dir",
        modes=frozenset({"character_build"}),
    ),
    "finalize_persona": _spec(
        "finalize_persona", "persona",
        "Save greeting and complete persona build",
        modes=frozenset({"character_build"}),
    ),
}

# Step-kind allowlists (canonical tool names)
STEP_KIND_TOOLS: dict[str, frozenset[str]] = {
    "explore": frozenset({
        "get_directory_tree", "read_code_outline", "grep_repo", "read_file_smart",
        "read_file", "read_file_region", "list_directory", "search_files",
        "web_search", "read_webpage", "save_research_note", "read_all_research_notes",
        "semantic_code_search", "index_codebase_for_search", "subagent_explore",
    }),
    "search": frozenset({"web_search", "read_webpage", "save_research_note", "read_all_research_notes", "grep_repo"}),
    "read": frozenset({
        "read_webpage", "read_file", "read_file_smart", "read_file_region",
        "save_research_note", "get_directory_tree", "read_code_outline", "grep_repo", "list_directory",
    }),
    "code": frozenset({
        "read_code_outline", "read_file_region", "grep_repo", "get_directory_tree",
        "write_project_markdown", "append_project_markdown", "replace_lines",
        "apply_patch", "apply_unified_patch",
        "replace_symbol", "run_pytest", "run_linter", "sync_project_to_disk", "list_directory",
        "run_command", "git_status", "git_diff",
    }),
    "verify": frozenset({
        "run_pytest", "run_linter", "grep_repo", "read_file_region",
        "get_directory_tree", "read_code_outline", "run_command", "git_diff",
    }),
    "synthesize": frozenset({
        "save_research_note", "read_all_research_notes", "summarize_sources",
        "write_project_markdown", "write_section",
    }),
    "write": frozenset({"init_document", "write_section", "read_outline", "write_project_markdown"}),
    "finalize": frozenset({
        "compile_final_document", "write_project_markdown", "append_project_markdown",
        "save_task_deliverable", "finish_task", "save_research_note",
        "read_file", "read_file_smart", "read_file_region",
        "write_persona_file", "finalize_persona",
    }),
    "tdd_red": frozenset({"run_pytest", "create_buffer_file", "replace_lines", "read_code_outline", "read_file_region"}),
    "tdd_green": frozenset({
        "run_pytest", "replace_lines", "apply_patch", "apply_unified_patch",
        "replace_symbol", "sync_project_to_disk",
    }),
    "tdd_refactor": frozenset({"run_pytest", "run_linter", "replace_lines", "apply_patch", "apply_unified_patch"}),
}

MODE_REQUIRED: dict[str, frozenset[str]] = {
    "code": frozenset({
        "init_code_project", "import_codebase", "attach_existing_repo",
        "read_code_outline", "read_file_region", "replace_lines", "apply_unified_patch",
        "apply_patch", "replace_symbol", "create_buffer_file", "run_pytest", "run_linter",
        "sync_project_to_disk", "write_project_markdown", "append_project_markdown",
    }),
    "research": frozenset({"web_search", "read_webpage", "save_research_note", "read_all_research_notes"}),
    "writing": frozenset({"init_document", "write_section", "read_outline", "compile_final_document"}),
    "character_build": frozenset({
        "web_search", "read_webpage", "save_research_note",
        "write_persona_file", "finalize_persona",
    }),
}

# Persona build: strict per-step tool sets (ignore semantic router extras).
CHARACTER_BUILD_READ_TOOLS = frozenset({
    "save_research_note",
})

CHARACTER_BUILD_SEARCH_TOOLS = frozenset({
    "web_search",
    "read_webpage",
    "save_research_note",
})

CHARACTER_BUILD_SYNTHESIZE_TOOLS = frozenset({
    "read_all_research_notes",
    "write_persona_file",
})

CHARACTER_BUILD_FINALIZE_TOOLS = frozenset({
    "finalize_persona",
})

# Generic workspace file tools must not write initialization.md during persona build.
CHARACTER_BUILD_FORBIDDEN_FILE_TOOLS = frozenset({
    "write_file",
    "replace_in_file",
    "replace_lines",
    "apply_patch",
    "apply_unified_patch",
    "replace_symbol",
    "write_project_markdown",
    "append_project_markdown",
    "read_file",
    "read_file_smart",
    "read_file_lines",
    "read_file_region",
})


def resolve_tool_name(name: str) -> tuple[str, str | None]:
    """Return (canonical_name, deprecation_warning_or_none)."""
    if name in TOOL_ALIASES:
        canonical = TOOL_ALIASES[name]
        return canonical, f"⚠️ deprecated tool name '{name}'; use '{canonical}'."
    return name, None


def routing_document_for_tool(name: str, description: str) -> str:
    spec = TOOL_SPECS.get(name)
    if spec:
        parts = [f"Tool: {name}. {spec.summary}"]
        if spec.use_when:
            parts.append(f"USE WHEN: {spec.use_when}")
        if spec.do_not_use:
            parts.append(f"DO NOT USE: {spec.do_not_use}")
        return " ".join(parts)
    return f"Tool Name: {name}. Description: {description or ''}"


def get_mode_playbook(mode: str) -> str:
    lines = [f"## Tool playbook ({mode} mode)", ""]
    if mode == "code":
        lines.append(
            "Recon: get_directory_tree then read_code_outline once. "
            "Search: grep_repo. Read: read_file_region. "
            "Docs: write_project_markdown. Edit: replace_lines / apply_patch."
        )
    elif mode == "research":
        lines.append("web_search then save_research_note; synthesize on finalize with final_report.")
    elif mode == "writing":
        lines.append("init_document, write_section, compile_final_document.")
    elif mode == "character_build":
        lines.append(
            "Ingest attachments via save_research_note; optional web_search. "
            "write_persona_file initialization.md (rich character bible), then finalize_persona."
        )
    else:
        lines.append("grep_repo and read_file_smart for files; save_research_note for progress.")
    lines.append("Work continuously across tool results until the step objective is done.")
    return "\n".join(lines)


def build_executable_registry() -> dict:
    from tools import SURVIVAL_TOOLS

    try:
        from tool_library import ALL_TOOLS
    except ImportError:
        ALL_TOOLS = {}

    merged = {**SURVIVAL_TOOLS, **ALL_TOOLS}
    out = {k: v for k, v in merged.items() if k not in INTERNAL_TOOL_NAMES}

    # Register alias names pointing at canonical func
    for alias, canonical in TOOL_ALIASES.items():
        if canonical in out and alias not in out:
            meta = dict(out[canonical])
            desc = meta.get("description", "")
            meta["description"] = f"(alias of {canonical}) {desc}"
            meta["_canonical"] = canonical
            out[alias] = meta
    return out


def allowed_tools_for_step(
    *,
    mode: str,
    step_kind: str,
    routed: set[str],
    all_names: set[str],
    objective: str = "",
    user_request: str = "",
    persona_research_lore: bool = False,
) -> set[str]:
    from recon_policy import pinned_tools_for_code_step

    meta = frozenset({"mark_objective_complete", "finish_task"})

    if mode == "character_build":
        if step_kind == "search" and persona_research_lore:
            pool = CHARACTER_BUILD_SEARCH_TOOLS | meta
        elif step_kind == "read":
            pool = CHARACTER_BUILD_READ_TOOLS | meta
        elif step_kind == "synthesize":
            pool = CHARACTER_BUILD_SYNTHESIZE_TOOLS | meta
        elif step_kind == "finalize":
            pool = CHARACTER_BUILD_FINALIZE_TOOLS | meta
        else:
            pool = set(routed) | MODE_REQUIRED.get(mode, frozenset()) | meta
        return {n for n in pool if n in all_names or n in TOOL_ALIASES}

    allowed = set(routed)
    allowed |= meta
    allowed |= MODE_REQUIRED.get(mode, frozenset())

    filt = STEP_KIND_TOOLS.get(step_kind)
    names_ok = all_names | set(TOOL_ALIASES.keys())
    if filt is not None:
        pool = allowed | {n for n in filt if n in names_ok}
        allowed = {
            n
            for n in pool
            if n in filt
            or n in MODE_REQUIRED.get(mode, frozenset())
            or n in ("mark_objective_complete", "finish_task")
        }

    if mode == "code":
        allowed |= set(
            pinned_tools_for_code_step(step_kind, objective=objective, user_request=user_request)
        )

    return {n for n in allowed if n in all_names or n in TOOL_ALIASES}
