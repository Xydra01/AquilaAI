import pytest
import sys
import os
import inspect
from unittest.mock import patch, MagicMock

# Add the parent 'agent' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

# We must instantiate a QApplication before creating any QWidgets for testing
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app

import gui

# Dynamically find the main window class
MainWindowClass = next(
    (obj for name, obj in inspect.getmembers(gui) 
     if inspect.isclass(obj) and issubclass(obj, QMainWindow) and obj is not QMainWindow), 
    None
)

def test_agent_worker_signals(qtbot, qapp):
    """TDD Goal: Ensure the background worker correctly emits the finished signal when the LLM completes."""
    worker = gui.AgentWorker(task_name="test_task", prompt="Do something", mode="Task")
    
    # Mock the LLM's unified task runner so the test runs instantly and doesn't hit the API
    mock_agent = MagicMock()
    mock_agent.run_unified_task.return_value = "✅ Task complete!"
    with patch('gui.get_agent', return_value=mock_agent):
        # Use qtbot to wait for the background thread to emit the finished_signal
        with qtbot.waitSignal(worker.finished_signal, timeout=2000) as blocker:
            worker.start()
            
        # Verify the signal carried the exact result from the mock (including the worker's prepend string)
        assert blocker.args == ["✅ Task Completed:\n✅ Task complete!"]
        assert mock_agent.run_unified_task.called

def test_ui_button_states_on_finish(qtbot, qapp):
    """TDD Goal: Ensure the Stop button disables and Run/Resume re-enable when a task finishes."""
    if not MainWindowClass:
        pytest.skip("Main window class not found in gui.py")
        
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.mode_selector.setCurrentText("Autonomous Task")
    page = window.autonomous_page

    page.run_btn.setDisabled(True)
    page.stop_btn.setDisabled(False)
    window.task_finished("✅ Done!")

    assert page.run_btn.isEnabled() is True
    assert page.resume_btn.isEnabled() is True
    assert page.stop_btn.isEnabled() is False

def test_chat_history_appends_result(qtbot, qapp):
    """TDD Goal: Ensure that when a task finishes, the result is appended to the chat UI."""
    if not MainWindowClass:
        pytest.skip("Main window class not found in gui.py")
        
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.mode_selector.setCurrentText("Autonomous Task")

    window.task_finished("This is a test result.")

    chat_html = window.autonomous_page.chat_history.toHtml()
    
    # Verify the agent's response was formatted and injected
    assert "This is a test result" in chat_html
    assert "Aquila:" in chat_html

def test_agent_worker_chat_streaming(qtbot, qapp):
    """TDD Goal: Ensure AgentWorker routes Chat mode to run_chat, passes payloads correctly, and streams tokens via ledger_signal."""
    
    mock_history = [{"role": "user", "content": "What is life?"}]
    mock_images = ["data:image/jpeg;base64,fake_image_data"]
    
    # The worker must now accept chat_history and attached_images 
    # so it can pass them directly to the global_agent.run_chat()
    worker = gui.AgentWorker(
        task_name="Chat", 
        prompt="Hi", 
        mode="Chat", 
        chat_history=mock_history,
        attached_images=mock_images
    )
    
    mock_agent = MagicMock()
    def mock_generator():
        yield {"message": {"content": "Stream "}}
        yield {"message": {"content": "Test!"}}
    mock_agent.run_chat.return_value = mock_generator()
    with patch('gui.get_agent', return_value=mock_agent):
        
        signals = []
        worker.ledger_signal.connect(signals.append)
        
        with qtbot.waitSignal(worker.finished_signal, timeout=2000) as blocker:
            worker.start()
            
        # 1. The worker must combine the chunks into a final string for finished_signal
        assert blocker.args == ["Stream Test!"]
        
        # 2. The worker must emit EACH chunk sequentially to the ledger_signal
        assert signals == ["Stream ", "Test!"]
        
        # 3. CRITICAL: The worker must pass the correct parameters to run_chat!
        assert mock_agent.run_chat.called
        args, kwargs = mock_agent.run_chat.call_args

        # Validate it routed the images, the history, and requested a stream via kwargs!
        assert kwargs.get("user_input") == "Hi"
        assert kwargs.get("chat_history") == mock_history
        assert kwargs.get("image_payloads") == mock_images
        assert kwargs.get("stream") is True

def test_stream_chat_token_ui_update(qtbot, qapp):
    """TDD Goal: Ensure stream_chat_token appends text without throwing Enum/Attribute errors."""
    if not MainWindowClass:
        pytest.skip("Main window class not found in gui.py")
        
    window = MainWindowClass()
    qtbot.addWidget(window)
    window.mode_selector.setCurrentText("Chat Mode")
    page = window.chat_page
    page.chat_history.clear()

    try:
        page.stream_chat_token("Hello")
        page.stream_chat_token(" World")
    except AttributeError as e:
        pytest.fail(f"stream_chat_token raised an AttributeError: {e}")

    assert "Hello World" in page.chat_history.toPlainText()