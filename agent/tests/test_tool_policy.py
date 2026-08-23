import pytest

from agent.policies import (
    EXPLORE_TOOLS,
    META_TOOLS,
    build_allowed_tool_names,
    prioritize_tools_for_schema,
    schema_hint_tool_names,
)


def test_explore_tools_read_only():
    assert "write_file" not in EXPLORE_TOOLS
    assert "read_code_outline" in EXPLORE_TOOLS


def test_build_allowed_includes_meta_and_required(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "0")
    all_names = {
        "read_code_outline",
        "run_pytest",
        "replace_lines",
        "web_search",
        "mark_objective_complete",
        "finish_task",
        "write_file",
        "my_custom_tool",
    }
    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="explore",
        routed=["my_custom_tool"],
        all_tool_names=all_names,
    )
    assert "mark_objective_complete" in allowed
    assert "read_code_outline" in allowed
    assert "my_custom_tool" in allowed


def test_dynamic_work_palette_allows_edit_on_read_step(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        "read_file",
        "grep_repo",
        "replace_lines",
        "run_pytest",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="read",
        routed=[],
        all_tool_names=all_names,
    )
    assert "replace_lines" in allowed
    assert "run_pytest" in allowed


def test_legacy_code_read_step_excludes_web_search(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "0")
    all_names = {
        "read_file",
        "web_search",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="read",
        routed=[],
        all_tool_names=all_names,
    )
    assert "read_file" in allowed
    assert "web_search" not in allowed


def test_dynamic_code_read_excludes_web_search(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        "read_file",
        "web_search",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="read",
        routed=["web_search"],
        all_tool_names=all_names,
    )
    assert "read_file" in allowed
    assert "web_search" not in allowed


def test_dynamic_research_palette_excludes_writing_finalize_tools(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        "web_search",
        "read_webpage",
        "save_research_note",
        "read_all_research_notes",
        "compile_final_document",
        "append_project_markdown",
        "finalize_persona",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = build_allowed_tool_names(
        mode="research",
        step_kind="work",
        routed=[],
        all_tool_names=all_names,
    )
    assert "web_search" in allowed
    assert "compile_final_document" not in allowed
    assert "append_project_markdown" not in allowed
    assert "finalize_persona" not in allowed


def test_dynamic_research_blocks_routed_cross_mode_tools(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        "web_search",
        "save_research_note",
        "index_archive_sources",
        "git_status",
        "read_file_lines",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = build_allowed_tool_names(
        mode="research",
        step_kind="work",
        routed=["index_archive_sources", "git_status", "read_file_lines"],
        all_tool_names=all_names,
    )
    assert "web_search" in allowed
    assert "index_archive_sources" not in allowed
    assert "git_status" not in allowed
    assert "read_file_lines" not in allowed


def test_dynamic_minimal_palette_omits_routed_extras(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        "web_search",
        "read_webpage",
        "save_research_note",
        "read_all_research_notes",
        "grep_repo",
        "get_directory_tree",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = build_allowed_tool_names(
        mode="research",
        step_kind="work",
        routed=["get_directory_tree"],
        all_tool_names=all_names,
        minimal_palette=True,
    )
    assert "web_search" in allowed
    assert "get_directory_tree" not in allowed


def test_schema_hint_puts_required_first():
    allowed = {
        "finish_task",
        "grep_repo",
        "index_archive_sources",
        "mark_objective_complete",
        "save_research_note",
        "web_search",
    }
    hint = schema_hint_tool_names(allowed, mode="research", limit=4)
    assert hint[0] in META_TOOLS
    assert "web_search" in hint
    assert "save_research_note" in hint
    assert "index_archive_sources" not in hint


def test_research_dynamic_palette_web_tools_only(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        "web_search",
        "read_webpage",
        "save_research_note",
        "read_all_research_notes",
        "grep_repo",
        "write_project_markdown",
        "append_project_markdown",
        "list_directory",
        "read_file",
        "mark_objective_complete",
        "finish_task",
        "compile_final_document",
    }
    allowed = build_allowed_tool_names(
        mode="research",
        step_kind="work",
        routed=["grep_repo", "write_project_markdown", "append_project_markdown"],
        all_tool_names=all_names,
    )
    assert "web_search" in allowed
    assert "save_research_note" in allowed
    for bad in (
        "grep_repo",
        "write_project_markdown",
        "append_project_markdown",
        "list_directory",
        "read_file",
        "compile_final_document",
    ):
        assert bad not in allowed, bad





def test_prioritize_tools_for_schema_keeps_required_first():
    allowed = {
        "web_search",
        "read_webpage",
        "save_research_note",
        "read_all_research_notes",
        "compile_final_document",
        "append_project_markdown",
        "grep_repo",
        "finish_task",
        "mark_objective_complete",
    }
    trimmed = prioritize_tools_for_schema(
        allowed,
        routed=["grep_repo"],
        mode="research",
        max_tools=8,
    )
    assert META_TOOLS <= trimmed
    assert "web_search" in trimmed
    assert "save_research_note" in trimmed
    assert "grep_repo" in trimmed
    assert "compile_final_document" not in trimmed


@pytest.mark.parametrize(
    "mode,forbidden",
    [
        (
            "code",
            (
                "compile_final_document",
                "finalize_persona",
                "web_search",
                "delegate_mode",
            ),
        ),
        (
            "writing",
            (
                "run_pytest",
                "finalize_persona",
                "init_code_project",
                "delegate_mode",
            ),
        ),
        (
            "task",
            (
                "compile_final_document",
                "run_pytest",
                "finalize_persona",
                "find_references",
            ),
        ),
        (
            "autonomous",
            (
                "compile_final_document",
                "finalize_persona",
                "write_syllabus_file",
            ),
        ),
    ],
)
def test_dynamic_palette_excludes_cross_mode_tools(monkeypatch, mode, forbidden):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    all_names = {
        *forbidden,
        "mark_objective_complete",
        "finish_task",
        "grep_repo",
        "read_file",
        "web_search",
        "save_research_note",
        "compile_final_document",
        "run_pytest",
        "init_document",
        "write_section",
        "delegate_mode",
    }
    allowed = build_allowed_tool_names(
        mode=mode,
        step_kind="work",
        routed=list(forbidden),
        all_tool_names=all_names,
    )
    for name in forbidden:
        assert name not in allowed, f"{name} should not be in {mode} dynamic palette"
    assert "mark_objective_complete" in allowed
    assert "finish_task" in allowed
