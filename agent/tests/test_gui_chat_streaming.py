import sys
import os
import inspect

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMainWindow
import gui


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


def test_chat_finished_does_not_duplicate_bubble(qtbot, qapp):
    """chat_finished should re-enable buttons without appending another Aquila bubble."""
    if not MainWindowClass:
        pytest.skip("Main window not found")
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.chat_history.clear()
    window.chat_history.append("<b>🦅 Aquila:</b><br>Hello from stream")
    before_count = window.chat_history.toHtml().count("Aquila:")
    window.worker = gui.AgentWorker("chat", "Hello", "chat")
    window.chat_finished("Hello from stream")
    after_html = window.chat_history.toHtml()
    assert after_html.count("Aquila:") == before_count
    assert window.run_btn.isEnabled()


def test_execute_task_chat_uses_chat_finished(qtbot, qapp, monkeypatch):
    if not MainWindowClass:
        pytest.skip("Main window not found")
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.chat_input.setText("Hi")
    window.mode_selector.setCurrentText("Chat Mode")

    from unittest.mock import patch, MagicMock

    def fake_run_chat(**kwargs):
        def gen():
            yield {"message": {"content": "Hey"}}
        return gen()

    with patch("gui.global_agent.run_chat", side_effect=fake_run_chat):
        window.execute_task()
        qtbot.waitUntil(lambda: window.run_btn.isEnabled(), timeout=3000)

    html = window.chat_history.toHtml()
    assert "Hey" in html
    assert html.count("🦅 Aquila") <= 2
