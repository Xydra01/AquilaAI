import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_catalog import (
    TOOL_ALIASES,
    build_executable_registry,
    resolve_tool_name,
    allowed_tools_for_step,
)


def test_aliases_resolve():
    canon, warn = resolve_tool_name("search_files")
    assert canon == "grep_repo"
    assert warn is not None


def test_build_registry_has_grep_repo():
    tools = build_executable_registry()
    assert "grep_repo" in tools
    assert "search_files" in tools


def test_allowed_tools_code_step():
    all_names = set(build_executable_registry().keys())
    allowed = allowed_tools_for_step(
        mode="code",
        step_kind="code",
        routed=set(),
        all_names=all_names,
    )
    assert "write_project_markdown" in allowed
    assert "grep_repo" in allowed
