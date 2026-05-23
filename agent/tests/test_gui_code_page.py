import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QPlainTextEdit
from gui_pages.code_ide_page import CodeIdePage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_code_editors_not_read_only(qapp, qtbot, tmp_path, monkeypatch):
    import json
    import gui

    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    state = {
        "project_name": "demo",
        "root": str(tmp_path / "proj"),
        "workspace_mode": "sandbox",
        "files": [{"path": "main.py", "content": "x = 1\n", "dirty": False, "lint_status": "ok"}],
    }
    (code_dir / "active_code_state.json").write_text(json.dumps(state), encoding="utf-8")

    window = gui.AquilaOS()
    qtbot.addWidget(window)
    page = CodeIdePage(window)
    page.refresh_state()
    assert page.editor_tabs.count() >= 1
    editor = page.editor_tabs.widget(0)
    assert isinstance(editor, QPlainTextEdit)
    assert editor.isReadOnly() is False
