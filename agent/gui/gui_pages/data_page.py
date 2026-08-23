"""Data Processing workspace: massive batch ingest and rule-based sorting."""
from __future__ import annotations

import os
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QLabel, QWidget,
    QPushButton, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt

from .base import BaseModePage
from ..gui_theme import SPLITTER_DEFAULTS, mode_accent_style
from ..gui_widgets.agent_rail import AgentRail
from ..gui_widgets.execution_log_panel import ExecutionLogPanel

class DataPage(BaseModePage):
    MODE = "data"
    MODE_LABEL = "Data Processing"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Data Processing Workspace")
        header.setStyleSheet(mode_accent_style("data"))
        layout.addWidget(header)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        self.agent_rail = AgentRail(main_window, compact_buttons=True)
        self.agent_rail.attach_button.setVisible(False)
        self.splitter.addWidget(self.agent_rail)

        middle = QWidget()
        mid_layout = QVBoxLayout(middle)
        
        mid_layout.addWidget(QLabel("1. Input Directory (Data to Process)"))
        in_row = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Select folder containing files to process...")
        in_btn = QPushButton("Browse...")
        in_btn.clicked.connect(self._browse_input)
        in_row.addWidget(self.input_line, stretch=1)
        in_row.addWidget(in_btn)
        mid_layout.addLayout(in_row)

        mid_layout.addWidget(QLabel("2. Output Directory (Where to sort/move files)"))
        out_row = QHBoxLayout()
        self.output_line = QLineEdit()
        self.output_line.setPlaceholderText("Select destination folder...")
        out_btn = QPushButton("Browse...")
        out_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_line, stretch=1)
        out_row.addWidget(out_btn)
        mid_layout.addLayout(out_row)

        mid_layout.addWidget(QLabel("Status"))
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        mid_layout.addWidget(self.status_box, stretch=1)

        self.splitter.addWidget(middle)

        self.log_panel = ExecutionLogPanel(main_window)
        self.splitter.addWidget(self.log_panel)
        self.splitter.setSizes(SPLITTER_DEFAULTS.get("data", [280, 520, 480]))

    def _browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Directory")
        if folder:
            self.input_line.setText(folder)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.output_line.setText(folder)

    # Implement required BaseModePage / AgentRail delegation methods
    def append_chat_html(self, html: str) -> None:
        self.agent_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        self.agent_rail.clear_chat_display()
        self.log_panel.reset_scroll_follow()

    def get_chat_input_text(self) -> str:
        prompt = self.agent_rail.get_chat_input_text().strip()
        in_dir = self.input_line.text().strip()
        out_dir = self.output_line.text().strip()
        if not prompt:
            prompt = "Process and sort the data."
        # Inject the directories into the prompt so the backend logic can parse them
        return f"[Data Mode Input: {in_dir}]\n[Data Mode Output: {out_dir}]\n\n{prompt}"

    def clear_chat_input(self) -> None:
        self.agent_rail.clear_chat_input()

    def set_run_buttons_running(self, running: bool) -> None:
        self.agent_rail.set_run_buttons_running(running)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        self.log_panel.update_ledger(text, clear=clear)

    def begin_assistant_stream(self) -> None:
        self.agent_rail.begin_assistant_stream()

    def finalize_streamed_message(self, raw_text: str) -> None:
        self.agent_rail.finalize_streamed_message(raw_text)

    def stream_chat_token(self, token: str) -> None:
        self.agent_rail.stream_chat_token(token)

    def stream_thinking_token(self, token: str) -> None:
        self.agent_rail.stream_thinking_token(token)

    def on_thinking_source(self, source: str) -> None:
        self.agent_rail.set_thinking_from_content(source == "content")

    @property
    def attach_button(self):
        return self.agent_rail.attach_button

    @property
    def chat_history(self):
        return self.agent_rail.chat_history

    @property
    def ledger_view(self):
        return self.log_panel.ledger_view

    @property
    def state_view(self):
        return self.log_panel.state_view

    def refresh_theme(self, *, dark: bool) -> None:
        self.agent_rail.refresh_theme(dark=dark)
        self.log_panel.refresh_theme(dark=dark)
        
    def refresh_state(self) -> None:
        pass
