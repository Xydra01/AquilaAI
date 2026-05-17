import json
import sys
import os
import inspect

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMainWindow
import gui
from gui_state import render_step_ledger_html, render_writing_draft_html
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
