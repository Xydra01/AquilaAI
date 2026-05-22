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


def test_import_codebase_sandbox(code_workspace):
    src = code_workspace / "sample_repo"
    (src / "src").mkdir(parents=True)
    (src / "src" / "app.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (src / "tests").mkdir()
    (src / "tests" / "test_app.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")

    result = code_canvas_tools.import_codebase(str(src), "sample", workspace_mode="sandbox")
    assert "✅ Imported" in result
    data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
    assert data["workspace_mode"] == "sandbox"
    assert data["root"] == "Agent-Code/sample"
    assert (code_workspace / "Agent-Code" / "sample" / "src" / "app.py").exists()
    assert len(data["files"]) == 2


def test_attach_existing_repo_in_place(code_workspace):
    src = code_workspace / "myrepo"
    src.mkdir()
    (src / "lib.py").write_text("x = 1\n", encoding="utf-8")

    result = code_canvas_tools.attach_existing_repo(str(src), "myrepo")
    assert "✅ Imported" in result
    data = json.loads(code_canvas_tools.active_code_file().read_text(encoding="utf-8"))
    assert data["workspace_mode"] == "in_place"
    assert data["files"][0]["path"] == "lib.py"
    assert data["files"][0].get("indexed_only") is True
