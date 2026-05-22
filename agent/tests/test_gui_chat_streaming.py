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
    window.mode_selector.setCurrentText("Chat Mode")
    page = window.chat_page
    page.chat_history.clear()
    page.chat_history.append("<b>🦅 Aquila:</b><br>Hello from stream")
    before_count = page.chat_history.toHtml().count("Aquila:")
    window.worker = gui.AgentWorker("chat", "Hello", "chat")
    window.chat_finished("Hello from stream")
    after_html = page.chat_history.toHtml()
    assert after_html.count("Aquila:") == before_count
    assert page.run_btn.isEnabled()


def test_execute_task_chat_uses_chat_finished(qtbot, qapp):
    """Chat worker run + chat_finished should surface streamed text without duplicate bubbles."""
    if not MainWindowClass:
        pytest.skip("Main window not found")
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.enter_workspace(window.active_instance_id)
    window.mode_selector.setCurrentText("Chat Mode")
    page = window.chat_page
    page.chat_history.clear()

    from unittest.mock import MagicMock, patch

    def fake_run_chat(**kwargs):
        def gen():
            yield {"message": {"content": "Hey"}}

        return gen()

    mock_agent = MagicMock()
    mock_agent.run_chat.side_effect = fake_run_chat
    worker = gui.AgentWorker("chat", "Hi", "chat", instance_id=window.active_instance_id)
    with patch("gui.get_agent", return_value=mock_agent):
        with qtbot.waitSignal(worker.finished_signal, timeout=5000):
            worker.run()

    window.worker = worker
    window.chat_finished("Hey")
    assert mock_agent.run_chat.called
    assert any(
        m.get("content") == "Hey"
        for m in window._chat_history_messages
        if m.get("role") == "assistant"
    )
    assert page.run_btn.isEnabled()
