"""Chat-only workspace (single column)."""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton
from PySide6.QtGui import QTextCursor

from gui_pages.base import BaseModePage


class ChatPage(BaseModePage):
    MODE = "chat"
    MODE_LABEL = "Chat Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Say hello or ask a question...")
        self.chat_input.returnPressed.connect(main_window.execute_task)
        self.attach_button = QPushButton("📎 Attach")
        self.attach_button.clicked.connect(main_window.open_attachment_dialog)
        self.run_btn = QPushButton("▶️ Send")
        self.run_btn.clicked.connect(main_window.execute_task)
        self.stop_btn = QPushButton("🛑 Stop")
        self.stop_btn.clicked.connect(main_window.stop_task)
        self.stop_btn.setDisabled(True)
        self.clear_chat_btn = QPushButton("🧹 Clear")
        self.clear_chat_btn.clicked.connect(main_window.clear_chat_display)
        for w in (
            self.attach_button,
            self.run_btn,
            self.stop_btn,
            self.clear_chat_btn,
        ):
            row.addWidget(w)
        layout.addWidget(self.chat_input)
        layout.addLayout(row)

    def append_chat_html(self, html: str) -> None:
        self.chat_history.append(html)

    def clear_chat_display(self) -> None:
        self.chat_history.clear()

    def get_chat_input_text(self) -> str:
        return self.chat_input.text().strip()

    def clear_chat_input(self) -> None:
        self.chat_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.stop_btn.setDisabled(not running)

    def stream_chat_token(self, token: str) -> None:
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.chat_history.setTextCursor(cursor)
