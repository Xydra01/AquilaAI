import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import is_ignored_code_path, should_skip_dir
from tool_library import code_canvas_tools


def test_should_skip_venv():
    assert should_skip_dir(".venv") is True
    assert should_skip_dir("node_modules") is True
    assert should_skip_dir("src") is False


def test_is_ignored_code_path():
    assert is_ignored_code_path(".venv/lib/site-packages/foo.py") is True
    assert is_ignored_code_path("src/app.py") is False


def test_import_skips_venv_tree(code_workspace):
    """Import must not pull thousands of files from .venv."""
    src = code_workspace / "repo"
    (src / "src").mkdir(parents=True)
    (src / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    venv = src / ".venv" / "lib" / "site-packages" / "pkg"
    venv.mkdir(parents=True)
    for i in range(50):
        (venv / f"mod_{i}.py").write_text("x = 1\n", encoding="utf-8")

    result = code_canvas_tools.import_codebase(str(src), "repo", workspace_mode="sandbox")
    assert "✅ Imported" in result
    assert ".venv" in result or "not indexed" in result.lower()
    state = __import__("json").loads(
        code_canvas_tools.active_code_file().read_text(encoding="utf-8")
    )
    paths = [f["path"] for f in state["files"]]
    assert all(".venv" not in p for p in paths)
    assert any("main.py" in p for p in paths)
    assert state.get("dependency_hints", {}).get("venv_dir") == ".venv"


@pytest.fixture
def code_workspace(tmp_path, monkeypatch):
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    active = code_dir / "active_code_state.json"
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    yield tmp_path


def test_prune_removes_venv_from_buffer(code_workspace):
    code_canvas_tools.init_code_project("p", "", "python")
    state = code_canvas_tools._load_state()
    state["files"] = [
        {"path": "src/a.py", "content": "x", "line_count": 1},
        {"path": ".venv/lib/x.py", "content": "y", "line_count": 1},
    ]
    code_canvas_tools._save_state(state)
    out = code_canvas_tools.prune_ignored_buffer_files()
    assert "Pruned" in out
    state = code_canvas_tools._load_state()
    assert len(state["files"]) == 1
    assert state["files"][0]["path"] == "src/a.py"
