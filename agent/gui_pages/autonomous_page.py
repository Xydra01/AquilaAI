"""All-in-one 3-pane layout for Autonomous Task and Research modes."""
import json
from pathlib import Path

import markdown
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QLabel,
    QWidget,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from gui_formatting import format_ledger_html
from gui_pages.base import BaseModePage
from gui_richtext import (
    SmartScrollTextEdit,
    apply_panel_style,
    finalize_streamed_message,
    mark_stream_start,
)
from gui_state import (
    resolve_ledger_path,
    render_step_ledger_html,
    render_writing_draft_html,
)


class AutonomousPage(BaseModePage):
    MODE = "autonomous"
    MODE_LABEL = "Autonomous Task"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        self.chat_history = SmartScrollTextEdit()
        apply_panel_style(self.chat_history, "chat", dark=main_window.dark_mode)
        left_layout.addWidget(self.chat_history)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Assign a task or say hello...")
        self.chat_input.returnPressed.connect(main_window.execute_task)
        left_layout.addWidget(self.chat_input)

        btn_layout = QHBoxLayout()
        self.attach_button = QPushButton("📎 Attach Files")
        self.attach_button.clicked.connect(main_window.open_attachment_dialog)
        self.run_btn = QPushButton("▶️ Run")
        self.run_btn.clicked.connect(main_window.execute_task)
        self.resume_btn = QPushButton("📂 Resume Task")
        self.resume_btn.clicked.connect(main_window.resume_task_dialog)
        self.stop_btn = QPushButton("🛑 Stop")
        self.stop_btn.clicked.connect(main_window.stop_task)
        self.stop_btn.setDisabled(True)
        self.clear_chat_btn = QPushButton("🧹 Clear Chat View")
        self.clear_chat_btn.clicked.connect(main_window.clear_chat_display)
        for w in (
            self.attach_button,
            self.run_btn,
            self.resume_btn,
            self.stop_btn,
            self.clear_chat_btn,
        ):
            btn_layout.addWidget(w)
        left_layout.addLayout(btn_layout)

        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.addWidget(QLabel("📝 The Canvas"))
        self.canvas_tabs = QTabWidget()
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setFont(QFont("Courier New", 11))
        self.canvas_tabs.addTab(self.canvas_editor, "Preview")
        middle_layout.addWidget(self.canvas_tabs)

        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        self.tab_widget = QTabWidget()
        self.ledger_view = SmartScrollTextEdit()
        apply_panel_style(self.ledger_view, "ledger", dark=main_window.dark_mode)
        self.tab_widget.addTab(self.ledger_view, "Execution Log")
        self.state_view = QTextEdit()
        self.state_view.setReadOnly(True)
        self.state_view.setFont(QFont("Consolas", 10))
        self.tab_widget.addTab(self.state_view, "Task State Tracker")
        right_layout.addWidget(self.tab_widget)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.middle_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([300, 600, 500])

    def append_chat_html(self, html: str) -> None:
        self.chat_history.append_smart(html)

    def clear_chat_display(self) -> None:
        self.chat_history.clear()
        self.chat_history.reset_scroll_follow()
        self.ledger_view.reset_scroll_follow()

    def get_chat_input_text(self) -> str:
        return self.chat_input.text().strip()

    def clear_chat_input(self) -> None:
        self.chat_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.resume_btn.setDisabled(running)
        self.stop_btn.setDisabled(not running)

    def refresh_theme(self, *, dark: bool) -> None:
        apply_panel_style(self.chat_history, "chat", dark=dark)
        apply_panel_style(self.ledger_view, "ledger", dark=dark)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        html = format_ledger_html(text)
        if clear:
            self.ledger_view.set_html_smart(html)
        else:
            self.ledger_view.append_smart(html)

    def begin_assistant_stream(self) -> None:
        mark_stream_start(self.chat_history)

    def finalize_streamed_message(self, raw_text: str) -> None:
        finalize_streamed_message(self.chat_history, raw_text)

    def refresh_state(self) -> None:
        if not self._worker:
            return
        mode = self._worker.mode.lower()
        state_path = resolve_ledger_path(mode, self._worker.task_name)
        if not state_path or not state_path.exists():
            self.state_view.setHtml(
                "<p style='color: #7f8c8d;'>No active ledger file yet.</p>"
            )
            return
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            if mode == "writing" or state_path.name == "active_draft_state.json":
                self.state_view.setHtml(render_writing_draft_html(state_data))
                title = state_data.get("title", "Draft")
                canvas_text = f"# {title}\n\n"
                for sec in state_data.get("sections", []):
                    canvas_text += (
                        f"## {sec.get('header', '')}\n{sec.get('content', '')}\n\n"
                    )
                canvas_html = markdown.markdown(
                    canvas_text, extensions=["fenced_code", "tables"]
                )
                self.canvas_editor.setHtml(
                    f"<div style='font-family: Arial, sans-serif; line-height: 1.6;'>"
                    f"{canvas_html}</div>"
                )
                while self.canvas_tabs.count() > 1:
                    self.canvas_tabs.removeTab(1)
            else:
                self.state_view.setHtml(render_step_ledger_html(state_data))
                while self.canvas_tabs.count() > 1:
                    self.canvas_tabs.removeTab(1)
        except Exception:
            self.state_view.setHtml(
                "<p style='color: #e74c3c;'>Error reading ledger state.</p>"
            )

    def stream_chat_token(self, token: str) -> None:
        self.chat_history.insert_text_smart(token)
