import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import normalize_workspace_path
from tool_library import code_canvas_tools


def test_absolute_path_becomes_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    abs_tests = (tmp_path / "Agent-Code" / "proj" / "tests" / "t.py").resolve()
    rel = normalize_workspace_path(str(abs_tests))
    assert rel == "Agent-Code/proj/tests/t.py"


def test_sync_nested_project_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    active = code_dir / "active_code_state.json"
    code_canvas_tools.init_code_project("add_fn", "", "python")
    code_canvas_tools.create_buffer_file("tests/test_add.py", "def test_x(): pass\n")
    code_canvas_tools.sync_project_to_disk()
    assert (tmp_path / "Agent-Code" / "add_fn" / "tests" / "test_add.py").exists()
