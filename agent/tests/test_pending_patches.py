import json
from pathlib import Path

import pytest


@pytest.fixture
def code_state(tmp_path, monkeypatch):
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    state_file = code_dir / "active_code_state.json"
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    state = {
        "project_name": "p",
        "root": str(tmp_path / "proj"),
        "workspace_mode": "sandbox",
        "files": [{"path": "a.py", "content": "x = 1\n", "line_count": 1}],
        "test_targets": [],
    }
    state_file.write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "proj").mkdir()
    return state_file


def test_queue_patch_when_review_enabled(code_state, monkeypatch):
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "1")
    monkeypatch.setattr(
        "tool_library.code_canvas_tools._should_queue_patch",
        lambda: True,
    )
    from tool_library import code_canvas_tools

    msg = code_canvas_tools.replace_lines("a.py", 1, 1, "x = 2\n")
    assert "queued" in msg.lower()
    pending = code_canvas_tools.list_pending_patches()
    assert len(pending) == 1
    assert pending[0]["path"] == "a.py"
