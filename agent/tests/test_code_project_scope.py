import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_library import code_canvas_tools
from tool_library import coding_tools
from loop_engine import LoopEngine


@pytest.fixture
def code_workspace(tmp_path, monkeypatch):
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    active = code_dir / "active_code_state.json"
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    yield tmp_path


def test_get_active_project_scope(code_workspace):
    code_canvas_tools.init_code_project("myapp", "", "python")
    scope = code_canvas_tools.get_active_project_scope()
    assert scope is not None
    assert scope["root"] == "Agent-Code/myapp"


@patch("tool_library.coding_tools._index_codebase")
def test_semantic_search_defaults_to_project_root(mock_index, code_workspace):
    code_canvas_tools._save_state({
        "project_name": "scoped",
        "root": "Agent-Code/scoped",
        "files": [],
        "test_targets": [],
    })
    mock_col = MagicMock()
    mock_col.query.return_value = {"documents": [[]], "metadatas": [[]]}
    mock_index.return_value = mock_col

    coding_tools.semantic_code_search("query", "")

    mock_index.assert_called_once()
    assert mock_index.call_args[0][0] == "Agent-Code/scoped"


def test_loop_step_entry_includes_code_project_root(code_workspace):
    code_canvas_tools.init_code_project("proj", "", "python")
    engine = LoopEngine(
        client=None,
        executor=None,
        console=None,
        action_schema={},
        system_prompt="",
        mode="code",
        mode_label="Code",
        plan_dir="Agent-Tasks",
    )
    msgs = engine._build_step_entry_messages("t1", "tdd_red")
    body = msgs[0]["content"]
    assert "CODE_PROJECT_ROOT: Agent-Code/proj" in body
    assert "SCOPE:" in body


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
    from tools import get_code_project_root, read_file, resolve_tool_path

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
    from tools import write_file

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
