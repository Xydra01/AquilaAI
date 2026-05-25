import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_library import code_canvas_tools


@pytest.fixture
def code_workspace(tmp_path, monkeypatch):
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    active = code_dir / "active_code_state.json"
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    yield tmp_path


def test_init_code_project(code_workspace):
    result = code_canvas_tools.init_code_project("hello_api", ".", "python")
    assert "✅ Code project 'hello_api' initialized" in result
    assert "Agent-Code/hello_api" in result
    assert code_canvas_tools.active_code_file().exists()
    data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
    assert data["project_name"] == "hello_api"
    assert data["root"] == "Agent-Code/hello_api"
    assert data["language_primary"] == "python"
    assert data["files"] == []


def test_create_and_replace_lines(code_workspace):
    code_canvas_tools.init_code_project("p", ".", "python")
    code_canvas_tools.create_buffer_file("src/a.py", "line1\nline2\nline3\n")
    result = code_canvas_tools.replace_lines("src/a.py", 2, 2, "LINE2\n")
    assert "✅ Replaced lines" in result
    data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
    content = data["files"][0]["content"]
    assert "LINE2" in content
    assert "line2" not in content


def test_sync_project_to_disk(code_workspace):
    code_canvas_tools.init_code_project("sync_proj", ".", "python")
    code_canvas_tools.create_buffer_file("out.py", "x = 1\n")
    result = code_canvas_tools.sync_project_to_disk()
    assert "✅ Synced" in result
    assert (code_workspace / "Agent-Code" / "sync_proj" / "out.py").exists()
    data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
    assert data["files"][0]["dirty"] is False


def test_read_code_outline_empty(code_workspace):
    code_canvas_tools.init_code_project("outline", ".", "python")
    outline = code_canvas_tools.read_code_outline()
    assert "PROJECT: outline" in outline
    assert "no source files" in outline.lower()


def test_apply_unified_patch(code_workspace):
    code_canvas_tools.init_code_project("patch", ".", "python")
    code_canvas_tools.create_buffer_file("f.py", "alpha\nbeta\n")
    patch = """--- a/f.py
+++ b/f.py
@@ -1,2 +1,2 @@
 alpha
-beta
+gamma
"""
    result = code_canvas_tools.apply_unified_patch("f.py", patch)
    assert "✅ Patched" in result
    data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
    assert "gamma" in data["files"][0]["content"]
    assert "beta" not in data["files"][0]["content"]


def test_run_pytest_updates_state(code_workspace):
    from unittest.mock import patch
    from language_registry import TestResult

    with patch("language_registry.run_tests") as mock_run:
        mock_run.return_value = TestResult(True, 2, 0, "ok", "2 passed")
        code_canvas_tools.init_code_project("t", ".", "python")
        code_canvas_tools.create_buffer_file("m.py", "def f(): pass\n")
        code_canvas_tools.set_test_targets("m.py")
        out = code_canvas_tools.run_pytest("")
        assert "pytest" in out.lower()
        data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
        assert data["files"][0]["last_test"] == "passed"
