import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_library import code_canvas_tools
from tool_library import coding_tools


@pytest.fixture
def code_workspace(tmp_path, monkeypatch):
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    yield tmp_path


def test_get_active_project_scope(code_workspace):
    code_canvas_tools.init_code_project("myapp", "", "python")
    scope = code_canvas_tools.get_active_project_scope()
    assert scope is not None
    assert scope["root"] == "Agent-Code/myapp"


@patch.object(coding_tools, "index_code_project")
def test_semantic_search_defaults_to_project_root(mock_index, code_workspace):
    scoped = code_workspace / "Agent-Code" / "scoped"
    scoped.mkdir(parents=True)
    code_canvas_tools._save_state({
        "project_name": "scoped",
        "root": "Agent-Code/scoped",
        "files": [],
        "test_targets": [],
    })
    mock_col = MagicMock()
    mock_col.query.return_value = {"documents": [[]], "metadatas": [[]]}
    mock_index.return_value = mock_col

    result = coding_tools.semantic_code_search("query", "")

    mock_index.assert_called_once()
    assert "No relevant code found" in result


def test_resolve_tool_path_and_read_file_in_place(code_workspace):
    proj = code_workspace / "TheProject"
    (proj / "backend").mkdir(parents=True)
    (proj / "backend" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    code_canvas_tools._save_state({
        "project_name": "TheProject",
        "root": str(proj),
        "workspace_mode": "in_place",
        "files": [],
        "test_targets": [],
    })
    from agent.core import get_code_project_root, read_file, resolve_tool_path

    assert get_code_project_root() == proj.resolve()
    assert resolve_tool_path("backend/main.py") == (proj / "backend" / "main.py").resolve()
    assert "print('hi')" in read_file("backend/main.py")


def test_search_files_scoped_to_project(code_workspace):
    proj = code_workspace / "scoped_repo"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (code_workspace / "distractor.py").write_text("y = 2\n", encoding="utf-8")
    code_canvas_tools._save_state({
        "project_name": "scoped_repo",
        "root": str(proj),
        "workspace_mode": "in_place",
        "files": [],
        "test_targets": [],
    })
    from tool_library.os_tools import search_files

    result = search_files("*.py", ".")
    assert "app.py" in result
    assert str(proj) in result
    assert "distractor.py" not in result


def test_write_file_blocked_outside_project(code_workspace):
    proj = code_workspace / "proj"
    proj.mkdir()
    code_canvas_tools._save_state({
        "project_name": "proj",
        "root": str(proj),
        "workspace_mode": "in_place",
        "files": [],
        "test_targets": [],
    })
    from agent.core import write_file

    blocked = write_file("../escape.md", "nope")
    assert "CODE MODE" in blocked
    ok = write_file("ARCHITECTURE.md", "# Doc\n")
    assert "Successfully" in ok
    assert (proj / "ARCHITECTURE.md").read_text(encoding="utf-8") == "# Doc"


def test_write_project_markdown(code_workspace):
    proj = code_workspace / "proj"
    proj.mkdir()
    code_canvas_tools._save_state({
        "project_name": "proj",
        "root": str(proj),
        "workspace_mode": "in_place",
        "files": [],
        "test_targets": [],
    })
    body = "# Pink Sapphire Cove\n\n" + ("Overview of the cove project.\n" * 80)
    assert len(body) >= 1500
    result = code_canvas_tools.write_project_markdown("ARCHITECTURE.md", body)
    assert "✅" in result
    assert (proj / "ARCHITECTURE.md").read_text(encoding="utf-8").startswith("# Pink Sapphire Cove")


def test_resolve_tool_path_bypasses_project_for_global_data(code_workspace):
    proj = code_workspace / "proj"
    proj.mkdir()
    code_canvas_tools._save_state({
        "project_name": "proj",
        "root": str(proj),
        "workspace_mode": "in_place",
        "files": [],
        "test_targets": [],
    })
    from agent.core import resolve_tool_path
    
    # Create a draft file in the global drafts directory
    draft_dir = code_workspace / "Agent-Drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_file = draft_dir / "sqlite_wal_windows.md"
    draft_file.write_text("wal guide", encoding="utf-8")
    
    # 1. Resolve relative path to global draft file
    res_rel = resolve_tool_path("Agent-Drafts/sqlite_wal_windows.md")
    assert res_rel.resolve() == draft_file.resolve()
    
    # 2. Resolve absolute path to global draft file
    res_abs = resolve_tool_path(str(draft_file))
    assert res_abs.resolve() == draft_file.resolve()
    
    # 3. Resolve path with relative dot segments (one level up for the project root in test)
    res_dots = resolve_tool_path(f"../Agent-Drafts/sqlite_wal_windows.md")
    assert res_dots.resolve() == draft_file.resolve()
