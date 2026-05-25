"""Reusable agent chat rail: history, input, run controls."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

from gui_richtext import (
    SmartScrollTextEdit,
    apply_panel_style,
    finalize_streamed_message,
    mark_stream_start,
)


class AgentRail(QWidget):
    """Left or right column: chat history + input + standard task buttons."""

    def __init__(
        self,
        main_window,
        *,
        placeholder: str = "Assign a task or say hello...",
        show_resume: bool = True,
        show_clear: bool = True,
        compact_buttons: bool = False,
    ):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chat_history = SmartScrollTextEdit()
        apply_panel_style(self.chat_history, "chat", dark=main_window.dark_mode)
        layout.addWidget(self.chat_history)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText(placeholder)
        self.chat_input.returnPressed.connect(main_window.execute_task)
        layout.addWidget(self.chat_input)

        btn_layout = QHBoxLayout()
        attach_label = "📎" if compact_buttons else "📎 Attach Files"
        self.attach_button = QPushButton(attach_label)
        self.attach_button.clicked.connect(main_window.open_attachment_dialog)
        self.run_btn = QPushButton("▶️" if compact_buttons else "▶️ Run")
        self.run_btn.clicked.connect(main_window.execute_task)
        self.resume_btn = QPushButton("📂" if compact_buttons else "📂 Resume Task")
        self.resume_btn.clicked.connect(main_window.resume_task_dialog)
        self.stop_btn = QPushButton("🛑" if compact_buttons else "🛑 Stop")
        self.stop_btn.clicked.connect(main_window.stop_task)
        self.stop_btn.setDisabled(True)
        for w in (self.attach_button, self.run_btn, self.stop_btn):
            btn_layout.addWidget(w)
        if show_resume:
            btn_layout.addWidget(self.resume_btn)
        if show_clear:
            self.clear_chat_btn = QPushButton("🧹" if compact_buttons else "🧹 Clear Chat View")
            self.clear_chat_btn.clicked.connect(main_window.clear_chat_display)
            btn_layout.addWidget(self.clear_chat_btn)
        else:
            self.clear_chat_btn = None
        layout.addLayout(btn_layout)

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
        self.resume_btn.setDisabled(running)
        self.stop_btn.setDisabled(not running)

    def begin_assistant_stream(self) -> None:
        mark_stream_start(self.chat_history)

    def stream_chat_token(self, token: str) -> None:
        self.chat_history.insert_text_smart(token)

    def finalize_streamed_message(self, raw_text: str) -> None:
        finalize_streamed_message(self.chat_history, raw_text)
