import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_library.code_canvas_tools import apply_user_buffer_edit, init_code_project


def test_apply_user_buffer_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    init_code_project("edit_test", "", "python")
    from tool_library.code_canvas_tools import create_buffer_file

    create_buffer_file("main.py", "# start\n")
    result = apply_user_buffer_edit("main.py", "print('hi')\n")
    assert "✅" in result
    buf = tmp_path / "Agent-Code" / "active_code_state.json"
    state = json.loads(buf.read_text(encoding="utf-8"))
    entry = next(f for f in state["files"] if f["path"] == "main.py")
    assert "print('hi')" in entry["content"]
    assert entry.get("edited_by") == "user"
