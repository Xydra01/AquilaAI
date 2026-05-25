"""Per-step tool allowlists — driven by tool_catalog when available."""
from __future__ import annotations

from recon_policy import pinned_tools_for_code_step

try:
    from tool_catalog import (
        MODE_REQUIRED as MODE_REQUIRED,
        STEP_KIND_TOOLS as STEP_KIND_TOOL_FILTER,
        allowed_tools_for_step as _catalog_allowed,
    )
except ImportError:
    MODE_REQUIRED = {}
    STEP_KIND_TOOL_FILTER = {}

EXPLORE_TOOLS = frozenset({
    "read_file",
    "read_file_smart",
    "read_file_region",
    "grep_repo",
    "search_files",
    "search_in_file",
    "list_directory",
    "get_directory_tree",
    "read_code_outline",
    "index_codebase_for_search",
    "semantic_code_search",
    "read_webpage",
    "web_search",
    "save_research_note",
    "read_all_research_notes",
    "query_past_experience",
    "subagent_explore",
})

META_TOOLS = frozenset({
    "mark_objective_complete",
    "finish_task",
})

CODE_REQUIRED_TOOLS = frozenset({
    "init_code_project",
    "import_codebase",
    "attach_existing_repo",
    "read_code_outline",
    "read_file_region",
    "replace_lines",
    "apply_unified_patch",
    "apply_patch",
    "replace_symbol",
    "create_buffer_file",
    "run_pytest",
    "run_linter",
    "sync_project_to_disk",
    "write_project_markdown",
})

RESEARCH_REQUIRED_TOOLS = frozenset({
    "web_search",
    "read_webpage",
    "save_research_note",
    "read_all_research_notes",
})

WRITING_REQUIRED_TOOLS = frozenset({
    "init_document",
    "write_section",
    "read_outline",
    "compile_final_document",
})

if not STEP_KIND_TOOL_FILTER:
    STEP_KIND_TOOL_FILTER = {
        "explore": EXPLORE_TOOLS,
        "search": frozenset({"web_search", "read_webpage", "save_research_note", "read_all_research_notes", "grep_repo"}),
        "read": frozenset({
            "read_webpage", "read_file", "read_file_smart", "read_file_region", "save_research_note",
            "get_directory_tree", "read_code_outline", "grep_repo", "list_directory",
        }),
        "verify": frozenset({
            "run_pytest", "run_linter", "grep_repo", "read_file_region",
            "get_directory_tree", "read_code_outline", "run_command", "git_diff",
        }),
        "code": frozenset({
            "read_code_outline", "read_file_region", "grep_repo", "get_directory_tree",
            "write_project_markdown", "replace_lines", "apply_patch", "apply_unified_patch",
            "replace_symbol", "run_pytest", "run_linter", "sync_project_to_disk", "list_directory",
            "run_command", "git_status", "git_diff",
        }),
        "tdd_red": frozenset({"run_pytest", "create_buffer_file", "replace_lines", "read_code_outline", "read_file_region"}),
        "tdd_green": frozenset({"run_pytest", "replace_lines", "apply_patch", "apply_unified_patch", "replace_symbol", "sync_project_to_disk"}),
        "tdd_refactor": frozenset({"run_pytest", "run_linter", "replace_lines", "apply_patch", "apply_unified_patch"}),
    }

if not MODE_REQUIRED:
    MODE_REQUIRED = {
        "code": CODE_REQUIRED_TOOLS,
        "research": RESEARCH_REQUIRED_TOOLS,
        "writing": WRITING_REQUIRED_TOOLS,
    }


def required_tools_for_mode(mode: str) -> frozenset[str]:
    return frozenset(MODE_REQUIRED.get(mode, ()))


def build_allowed_tool_names(
    *,
    mode: str,
    step_kind: str,
    routed: list[str],
    all_tool_names: set[str],
    objective: str = "",
    user_request: str = "",
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> set[str]:
    try:
        return _catalog_allowed(
            mode=mode,
            step_kind=step_kind,
            routed=set(routed),
            all_names=all_tool_names,
            objective=objective,
            user_request=user_request,
            persona_research_lore=persona_research_lore,
            learn_syllabus_web=learn_syllabus_web,
        )
    except Exception:
        pass

    allowed = set(META_TOOLS) | required_tools_for_mode(mode) | set(routed)
    filt = STEP_KIND_TOOL_FILTER.get(step_kind)
    if filt is not None:
        allowed = {
            n
            for n in allowed
            if n in filt or n in META_TOOLS or n in required_tools_for_mode(mode)
        }
    if mode == "code":
        allowed |= set(
            pinned_tools_for_code_step(
                step_kind, objective=objective, user_request=user_request
            )
        )
    return {n for n in allowed if n in all_tool_names}
