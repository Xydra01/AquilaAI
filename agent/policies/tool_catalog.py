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

ALL_MODES = frozenset({
    "task",
    "code",
    "research",
    "writing",
    "autonomous",
    "character_build",
    "learn_syllabus_build",
})

STEP_KINDS_ALL = frozenset({
    "explore", "search", "read", "code", "verify", "synthesize", "write",
    "finalize", "tdd_red", "tdd_green", "tdd_refactor", "work",
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
        modes=frozenset({"research", "task", "autonomous", "character_build", "learn_syllabus_build"}),
    ),
    "read_webpage": _spec(
        "read_webpage", "web", "Fetch URL",
        modes=frozenset({"research", "task", "autonomous", "character_build", "learn_syllabus_build"}),
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
    "write_syllabus_file": _spec(
        "write_syllabus_file", "learn",
        "Write syllabus.json for active course build",
        modes=frozenset({"learn_syllabus_build"}),
    ),
    "finalize_course": _spec(
        "finalize_course", "learn",
        "Complete course build after syllabus written",
        modes=frozenset({"learn_syllabus_build"}),
    ),
    "generate_assessment": _spec(
        "generate_assessment", "learn",
        "Create tier-scaled assessment for a syllabus node",
        modes=frozenset({"learn_syllabus_build", "learn_tutor"}),
    ),
    "index_archive_sources": _spec(
        "index_archive_sources", "learn",
        "Index archive source files for semantic search",
        modes=frozenset({"learn_archive"}),
    ),
    "search_archive_sources": _spec(
        "search_archive_sources", "learn",
        "Search indexed archive sources",
        modes=frozenset({"learn_archive"}),
    ),
    "generate_archive_quiz": _spec(
        "generate_archive_quiz", "learn",
        "Write quiz markdown to archive outputs",
        modes=frozenset({"learn_archive"}),
    ),
    "generate_archive_study_doc": _spec(
        "generate_archive_study_doc", "learn",
        "Write study guide markdown to archive outputs",
        modes=frozenset({"learn_archive"}),
    ),
    "execute_sql_query": _spec(
        "execute_sql_query", "data",
        "Execute read-only SQL query against local SQLite DB",
        modes=frozenset({"task", "code", "research", "autonomous"}),
    ),
    "rest_api_client": _spec(
        "rest_api_client", "data",
        "Generic HTTP REST client for local/network APIs",
        modes=frozenset({"task", "code", "research", "autonomous"}),
    ),
    "open_application": _spec(
        "open_application", "desktop",
        "Launch native OS applications or files",
        modes=frozenset({"task", "autonomous"}),
    ),
    "import_calendar_ics": _spec(
        "import_calendar_ics", "calendar",
        "Import an ICS calendar file to the local DB",
        modes=frozenset({"task", "autonomous"}),
    ),
    "navigate_and_interact": _spec(
        "navigate_and_interact", "browser",
        "Navigate and interact with SPAs via local Playwright",
        modes=frozenset({"task", "autonomous", "research"}),
    ),
    "take_screenshot": _spec(
        "take_screenshot", "browser",
        "Take a local screenshot of a webpage",
        modes=frozenset({"task", "autonomous", "research"}),
    ),
    "analyze_image_local": _spec(
        "analyze_image_local", "multimodal",
        "Analyze a local image using a local vision model",
        modes=frozenset({"task", "autonomous", "research"}),
    ),
    "transcribe_audio_local": _spec(
        "transcribe_audio_local", "multimodal",
        "Transcribe local audio using local Whisper",
        modes=frozenset({"task", "autonomous", "research"}),
    ),
    "analyze_video_local": _spec(
        "analyze_video_local", "multimodal",
        "Analyze a local video using Whisper and local vision model",
        modes=frozenset({"task", "autonomous", "research"}),
    ),
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
    "learn_syllabus_build": frozenset({
        "web_search", "read_webpage", "save_research_note",
        "write_syllabus_file", "finalize_course", "generate_assessment",
    }),
    "learn_archive": frozenset({
        "index_archive_sources", "search_archive_sources",
        "generate_archive_quiz", "generate_archive_study_doc",
    }),
    "task": frozenset({"delegate_mode"}),
    "autonomous": frozenset({"delegate_mode"}),
}

# Curated interleavable tools per mode (no cross-mode finalize/persona/archive tools).
DYNAMIC_CORE_PALETTE: dict[str, frozenset[str]] = {
    "research": frozenset({
        "web_search", "read_webpage", "save_research_note", "read_all_research_notes",
        "summarize_sources", "query_past_experience",
        "execute_sql_query", "rest_api_client",
        "navigate_and_interact", "take_screenshot", "analyze_image_local", "transcribe_audio_local",
    }),
    "code": frozenset({
        "get_directory_tree", "read_code_outline", "grep_repo", "read_file",
        "read_file_region", "read_file_smart", "list_directory", "search_files",
        "search_in_file", "semantic_code_search", "index_codebase_for_search",
        "init_code_project", "import_codebase", "attach_existing_repo",
        "replace_lines", "apply_patch", "apply_unified_patch", "replace_symbol",
        "create_buffer_file", "write_project_markdown", "append_project_markdown",
        "sync_project_to_disk", "run_pytest", "run_linter", "run_command",
        "git_status", "git_diff",
    }),
    "writing": frozenset({
        "init_document", "write_section", "read_outline", "compile_final_document",
        "write_project_markdown", "append_project_markdown", "save_research_note",
        "read_all_research_notes",
    }),
    "task": frozenset({
        "delegate_mode", "save_research_note", "read_all_research_notes", "query_past_experience",
        "ask_user", "read_file", "read_file_smart", "read_file_region", "read_file_lines",
        "list_directory", "get_directory_tree", "grep_repo", "search_files", "search_in_file",
    }),
    "autonomous": frozenset({
        "delegate_mode", "save_research_note", "read_all_research_notes", "query_past_experience",
        "ask_user", "read_file", "read_file_smart", "read_file_region", "read_file_lines",
        "list_directory", "get_directory_tree", "grep_repo", "search_files", "search_in_file",
    }),
}

# Strip cross-mode / archive / persona tools even when the semantic router suggests them.
DYNAMIC_EXCLUDED_BY_MODE: dict[str, frozenset[str]] = {
    "research": frozenset({
        "compile_final_document", "init_document", "write_section", "read_outline",
        "write_persona_file", "finalize_persona", "write_syllabus_file", "finalize_course",
        "generate_archive_quiz", "generate_archive_study_doc", "generate_assessment",
        "index_archive_sources", "search_archive_sources",
        "init_code_project", "import_codebase", "attach_existing_repo",
        "run_pytest", "run_linter", "replace_lines", "apply_patch", "apply_unified_patch",
        "replace_symbol", "create_buffer_file", "sync_project_to_disk", "delegate_mode",
        "append_project_markdown", "write_project_markdown", "find_references",
        "write_file", "replace_in_file", "git_status", "git_diff", "run_command",
        "read_file_lines", "read_file_smart", "read_file", "read_file_region",
        "get_directory_tree", "read_code_outline", "grep_repo", "list_directory",
        "search_files", "search_in_file", "semantic_code_search", "index_codebase_for_search",
        "subagent_explore",
    }),
    "code": frozenset({
        "compile_final_document", "init_document", "write_section", "read_outline",
        "write_persona_file", "finalize_persona", "write_syllabus_file", "finalize_course",
        "generate_archive_quiz", "generate_archive_study_doc", "generate_assessment",
        "index_archive_sources", "search_archive_sources",
        "web_search", "read_webpage", "summarize_sources", "delegate_mode",
        "save_research_note", "read_all_research_notes",
        "write_file", "replace_in_file", "execute_sql_query", "rest_api_client",
        "navigate_and_interact", "take_screenshot", "open_application", "import_calendar_ics",
        "analyze_image_local", "transcribe_audio_local", "analyze_video_local",
    }),
    "writing": frozenset({
        "run_pytest", "run_linter", "replace_lines", "apply_patch", "apply_unified_patch",
        "replace_symbol", "create_buffer_file", "sync_project_to_disk",
        "init_code_project", "import_codebase", "attach_existing_repo",
        "write_persona_file", "finalize_persona", "write_syllabus_file", "finalize_course",
        "generate_archive_quiz", "generate_archive_study_doc", "generate_assessment",
        "index_archive_sources", "search_archive_sources",
        "delegate_mode", "web_search", "read_webpage", "find_references",
        "read_file", "read_file_smart", "read_file_region", "read_file_lines",
        "list_directory", "get_directory_tree", "grep_repo", "search_files", "search_in_file",
        "write_file", "replace_in_file", "execute_sql_query", "rest_api_client",
        "navigate_and_interact", "take_screenshot", "run_command", "open_application",
        "import_calendar_ics", "analyze_image_local", "transcribe_audio_local", "analyze_video_local",
    }),
    "task": frozenset({
        "compile_final_document", "init_document", "write_section", "read_outline",
        "write_persona_file", "finalize_persona", "write_syllabus_file", "finalize_course",
        "generate_archive_quiz", "generate_archive_study_doc", "generate_assessment",
        "index_archive_sources", "search_archive_sources",
        "init_code_project", "import_codebase", "attach_existing_repo",
        "run_pytest", "run_linter", "replace_lines", "apply_patch", "apply_unified_patch",
        "replace_symbol", "create_buffer_file", "sync_project_to_disk",
        "append_project_markdown", "write_project_markdown", "find_references",
        "write_file", "replace_in_file", "git_status", "git_diff", "run_command",
        "web_search", "read_webpage", "summarize_sources",
        "navigate_and_interact", "take_screenshot", "execute_sql_query", "rest_api_client",
        "open_application", "import_calendar_ics", "analyze_image_local", "transcribe_audio_local", "analyze_video_local",
    }),
    "autonomous": frozenset({
        "compile_final_document", "init_document", "write_section", "read_outline",
        "write_persona_file", "finalize_persona", "write_syllabus_file", "finalize_course",
        "generate_archive_quiz", "generate_archive_study_doc", "generate_assessment",
        "index_archive_sources", "search_archive_sources",
        "init_code_project", "import_codebase", "attach_existing_repo",
        "run_pytest", "run_linter", "replace_lines", "apply_patch", "apply_unified_patch",
        "replace_symbol", "create_buffer_file", "sync_project_to_disk",
        "append_project_markdown", "write_project_markdown", "find_references",
        "write_file", "replace_in_file", "git_status", "git_diff", "run_command",
        "web_search", "read_webpage", "summarize_sources",
        "navigate_and_interact", "take_screenshot", "execute_sql_query", "rest_api_client",
        "open_application", "import_calendar_ics", "analyze_image_local", "transcribe_audio_local", "analyze_video_local",
    }),
}



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
    elif mode == "learn_syllabus_build":
        lines.append(
            "Build syllabus.json: ingest sources, optional web_search, "
            "write_syllabus_file once, finalize_course."
        )
    else:
        lines.append("grep_repo and read_file_smart for files; save_research_note for progress.")
    lines.append("Work continuously across tool results until the step objective is done.")
    return "\n".join(lines)


def build_executable_registry() -> dict:
    from agent.core import SURVIVAL_TOOLS

    try:
        from tool_library import ALL_TOOLS
    except ImportError:
        ALL_TOOLS = {}

    merged = {**SURVIVAL_TOOLS, **ALL_TOOLS}
    out = {k: v for k, v in merged.items() if k not in INTERNAL_TOOL_NAMES}

    try:
        from agent.core import delegate_mode

        out["delegate_mode"] = {
            "func": delegate_mode,
            "description": (
                "Delegate to a specialized mode (research|code|writing). "
                "Args: mode, objective, optional context."
            ),
        }
    except ImportError:
        pass

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
    learn_syllabus_web: bool = False,
    forbidden_tools: frozenset[str] | None = None,
    minimal_palette: bool = False,
) -> set[str]:
    meta = frozenset({"mark_objective_complete", "finish_task"})
    names_ok = all_names | set(TOOL_ALIASES.keys())
    deny = forbidden_tools or frozenset()
    excluded = DYNAMIC_EXCLUDED_BY_MODE.get(mode, frozenset())

    pool = set(meta)
    
    # Add all tools that belong to the current mode from spec metadata
    for name, spec in TOOL_SPECS.items():
        if mode in spec.modes:
            pool.add(name)
            
    # Add all tools from mode required and dynamic core palette
    pool.update(MODE_REQUIRED.get(mode, frozenset()))
    pool.update(DYNAMIC_CORE_PALETTE.get(mode, frozenset()))
    
    # Add routed tools to ensure dynamic integrations (e.g. MCP) are not lost
    pool.update(routed)

    pool -= deny
    pool -= excluded
    
    return {n for n in pool if n in names_ok}
