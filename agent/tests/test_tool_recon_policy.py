import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recon_policy import (
    CODE_RECON_PINNED,
    expand_code_documentation_plan,
    is_documentation_task,
    normalize_search_files_path,
    pinned_tools_for_code_step,
    routing_document_for_tool,
)
from tool_policy import build_allowed_tool_names
from loop_engine import LoopEngine
from path_visit_registry import PathVisitRegistry


def test_pinned_recon_on_code_explore():
    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="explore",
        routed=["list_directory"],
        all_tool_names={"list_directory", "get_directory_tree", "read_code_outline", "search_files"},
    )
    assert CODE_RECON_PINNED <= allowed


def test_doc_task_pins_write_markdown():
    pinned = pinned_tools_for_code_step(
        "code",
        objective="write ARCHITECTURE.md",
        user_request="Write ARCHITECTURE.md for The-Astral-Weyr",
    )
    assert "write_project_markdown" in pinned


def test_is_documentation_task_keywords():
    assert is_documentation_task("Write ARCHITECTURE.md for project")
    assert not is_documentation_task("implement feature with pytest")


def test_expand_code_documentation_plan_replaces_many_explore():
    plan = {
        "steps": [
            {"step_kind": "explore", "description": "a", "max_iterations": 8},
            {"step_kind": "explore", "description": "b", "max_iterations": 8},
            {"step_kind": "explore", "description": "c", "max_iterations": 8},
            {"step_kind": "read", "description": "d", "max_iterations": 5},
            {"step_kind": "read", "description": "e", "max_iterations": 5},
            {"step_kind": "read", "description": "f", "max_iterations": 5},
        ]
    }
    tuned, note = expand_code_documentation_plan(plan, "Write ARCHITECTURE.md")
    assert len(tuned["steps"]) == 4
    assert "Replaced" in note
    assert tuned["steps"][-2]["step_kind"] == "code"


def test_normalize_search_files_doubled_agent_code():
    path = "Agent-Code/The-Astral-Weyr/Agent-Code/The-Astral-Weyr"
    cleaned, note = normalize_search_files_path(path)
    assert "agent-code" not in cleaned.lower() or cleaned.count("agent-code") < 2
    assert note is not None


def test_resolve_tool_path_strips_agent_code_prefix(tmp_path, monkeypatch):
    from tools import resolve_tool_path
    from tool_library import code_canvas_tools

    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    project = code_dir / "The-Astral-Weyr"
    project.mkdir()
    active = code_dir / "active_code_state.json"
    active.write_text(
        '{"project_name": "The-Astral-Weyr", "root": "Agent-Code/The-Astral-Weyr", "workspace_mode": "in_place"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))

    resolved = resolve_tool_path("Agent-Code/The-Astral-Weyr")
    assert resolved == project.resolve()

    abs_path = str(project)
    resolved2 = resolve_tool_path(abs_path)
    assert resolved2 == project.resolve()


def test_routing_document_contains_use_when():
    doc = routing_document_for_tool("get_directory_tree", "Generates a tree.")
    assert "USE WHEN" in doc


def test_path_registry_blocks_third_list_directory():
    reg = PathVisitRegistry()
    reg.set_step_index(0)
    reg.record_tool("list_directory", {"path": "backend"})
    reg.record_tool("list_directory", {"path": "frontend"})
    msg = reg.check_list_directory("src")
    assert msg is not None
    assert "BLOCK" in msg


def test_explore_gate_passes_with_tree_and_read():
    blob = (
        "Tool 'get_directory_tree' result:\nDirectory Tree for: app/\n"
        "Tool 'read_file_region' result:\nLines 1-10"
    )
    assert LoopEngine._explore_advance_gate([], blob) is None


def test_explore_gate_passes_with_outline_and_search():
    blob = (
        "Tool 'read_code_outline' result:\nPROJECT: demo\n"
        "Tool 'index_codebase_for_search' result:\nindexed"
    )
    assert LoopEngine._explore_advance_gate([], blob) is None
