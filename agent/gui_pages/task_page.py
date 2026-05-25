"""Task workspace (autonomous): plan column, canvas preview, execution log."""
from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTextEdit,
    QTabWidget,
    QLabel,
    QWidget,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gui_pages.base import BaseModePage
from gui_theme import SPLITTER_DEFAULTS, mode_accent_style
from gui_widgets.agent_rail import AgentRail
from gui_widgets.execution_log_panel import ExecutionLogPanel
from gui_state import resolve_ledger_path, render_step_ledger_html


class TaskPage(BaseModePage):
    MODE = "autonomous"
    MODE_LABEL = "Autonomous Task"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Task Workspace")
        header.setStyleSheet(mode_accent_style("autonomous"))
        layout.addWidget(header)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        self.agent_rail = AgentRail(main_window)
        self.splitter.addWidget(self.agent_rail)

        middle = QWidget()
        mid_layout = QVBoxLayout(middle)
        mid_layout.addWidget(QLabel("Execution plan"))
        self.plan_list = QListWidget()
        mid_layout.addWidget(self.plan_list, stretch=1)
        mid_layout.addWidget(QLabel("Mode stack (future)"))
        self.stack_label = QLabel("Single-agent task run")
        self.stack_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        mid_layout.addWidget(self.stack_label)
        mid_layout.addWidget(QLabel("Output preview"))
        self.canvas_tabs = QTabWidget()
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setReadOnly(True)
        self.canvas_editor.setFont(QFont("Segoe UI", 11))
        self.canvas_tabs.addTab(self.canvas_editor, "Preview")
        mid_layout.addWidget(self.canvas_tabs, stretch=2)
        self.splitter.addWidget(middle)

        self.log_panel = ExecutionLogPanel(main_window)
        self.splitter.addWidget(self.log_panel)
        self.splitter.setSizes(SPLITTER_DEFAULTS.get("task", [280, 520, 480]))

    def _populate_plan(self, state_data: dict) -> None:
        self.plan_list.clear()
        steps = state_data.get("steps", [])
        current = state_data.get("current_step_index", 0)
        for i, step in enumerate(steps):
            desc = step.get("description", f"Step {i + 1}")
            kind = step.get("step_kind", "task")
            status = step.get("status", "pending")
            icon = "○"
            if status == "completed":
                icon = "✓"
            elif i == current:
                icon = "▶"
            item = QListWidgetItem(f"{icon} [{kind}] {desc[:80]}")
            item.setToolTip(f"Future mode stack: — | {desc}")
            self.plan_list.addItem(item)

    def append_chat_html(self, html: str) -> None:
        self.agent_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        self.agent_rail.clear_chat_display()
        self.log_panel.reset_scroll_follow()

    def get_chat_input_text(self) -> str:
        return self.agent_rail.get_chat_input_text()

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
        if not self._worker:
            return
        mode = self._worker.mode.lower()
        state_path = resolve_ledger_path(mode, self._worker.task_name)
        if not state_path or not state_path.exists():
            self.log_panel.set_state_html(
                "<p style='color: #7f8c8d;'>No active ledger file yet.</p>"
            )
            return
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            self._populate_plan(state_data)
            self.log_panel.set_state_html(render_step_ledger_html(state_data))
            deliverable = state_data.get("deliverable_preview", "")
            if deliverable:
                self.canvas_editor.setPlainText(str(deliverable)[:8000])
            else:
                self.canvas_editor.setPlainText(
                    "Task output will appear here as steps complete."
                )
            while self.canvas_tabs.count() > 1:
                self.canvas_tabs.removeTab(1)
        except Exception:
            self.log_panel.set_state_html(
                "<p style='color: #e74c3c;'>Error reading ledger state.</p>"
            )
