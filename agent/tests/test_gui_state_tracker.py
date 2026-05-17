import json
import sys
import os
import inspect

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMainWindow
import gui
from gui_state import (
    render_step_ledger_html,
    render_writing_draft_html,
    render_code_canvas_html,
    resolve_ledger_path,
)
from conftest import load_fixture_ledger


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


MainWindowClass = next(
    (
        obj
        for name, obj in inspect.getmembers(gui)
        if inspect.isclass(obj) and issubclass(obj, QMainWindow) and obj is not QMainWindow
    ),
    None,
)


def test_render_research_ledger_html():
    state = load_fixture_ledger("research_in_progress.json")
    html = render_step_ledger_html(state)
    assert "Search for primary sources" in html


def test_render_writing_draft_html():
    state = load_fixture_ledger("writing_draft.json")
    html = render_writing_draft_html(state)
    assert "Sample Essay" in html
    assert "Introduction" in html


def test_render_code_canvas_html():
    state = {
        "project_name": "api",
        "language_primary": "python",
        "files": [
            {
                "path": "src/main.py",
                "line_count": 10,
                "lint_status": "ok",
                "last_test": "passed",
                "dirty": False,
            }
        ],
        "test_targets": ["tests/test_api.py"],
    }
    html = render_code_canvas_html(state)
    assert "Code Canvas: api" in html
    assert "src/main.py" in html
    assert "test_api.py" in html


def test_resolve_ledger_path_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code_dir = tmp_path / "Agent-Code"
    code_dir.mkdir()
    buf = code_dir / "active_code_state.json"
    buf.write_text('{"project_name": "x"}', encoding="utf-8")
    p = resolve_ledger_path("code", "any_task")
    assert p.resolve() == buf.resolve()


def test_refresh_state_tracker_autonomous(qtbot, qapp, tmp_agent_dirs, write_ledger):
    if not MainWindowClass:
        pytest.skip("Main window not found")
    write_ledger(
        "Agent-Tasks/demo_task.json",
        load_fixture_ledger("autonomous_in_progress.json"),
    )
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.worker = gui.AgentWorker("demo_task", "test", "autonomous")
    window._refresh_state_tracker()
    html = window.state_view.toHtml()
    assert "Implement core module" in html or "Create project scaffold" in html


def test_refresh_state_tracker_research(qtbot, qapp, tmp_agent_dirs, write_ledger):
    if not MainWindowClass:
        pytest.skip("Main window not found")
    write_ledger(
        "Agent-Plans/research_job.json",
        load_fixture_ledger("research_in_progress.json"),
    )
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.worker = gui.AgentWorker("research_job", "test", "research")
    window._refresh_state_tracker()
    html = window.state_view.toHtml()
    assert "Search for primary sources" in html
