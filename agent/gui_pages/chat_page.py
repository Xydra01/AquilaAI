"""Chat-only workspace (single column)."""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton

from gui_pages.base import BaseModePage
from gui_richtext import (
    SmartScrollTextEdit,
    apply_panel_style,
    finalize_streamed_message,
    mark_stream_start,
)


class ChatPage(BaseModePage):
    MODE = "chat"
    MODE_LABEL = "Chat Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        self.chat_history = SmartScrollTextEdit()
        apply_panel_style(self.chat_history, "chat", dark=main_window.dark_mode)
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

    def refresh_theme(self, *, dark: bool) -> None:
        apply_panel_style(self.chat_history, "chat", dark=dark)

    def append_chat_html(self, html: str) -> None:
        self.chat_history.append_smart(html)

    def clear_chat_display(self) -> None:
        self.chat_history.clear()
        self.chat_history.reset_scroll_follow()

    def get_chat_input_text(self) -> str:
        return self.chat_input.text().strip()

    def clear_chat_input(self) -> None:
        self.chat_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.stop_btn.setDisabled(not running)

    def begin_assistant_stream(self) -> None:
        """Mark where streamed plain text starts (rendered on finish)."""
        mark_stream_start(self.chat_history)

    def stream_chat_token(self, token: str) -> None:
        self.chat_history.insert_text_smart(token)

    def finalize_streamed_message(self, raw_text: str) -> None:
        finalize_streamed_message(self.chat_history, raw_text)
