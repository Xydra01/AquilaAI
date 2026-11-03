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

from .base import BaseModePage
from ..gui_theme import SPLITTER_DEFAULTS, mode_accent_style
from ..gui_widgets.agent_rail import AgentRail
from ..gui_widgets.execution_log_panel import ExecutionLogPanel
from ..gui_state import resolve_ledger_path, render_step_ledger_html


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

        self.agent_rail = AgentRail(main_window, compact_buttons=True)
        self.splitter.addWidget(self.agent_rail)

        middle = QWidget()
        mid_layout = QVBoxLayout(middle)
        mid_layout.addWidget(QLabel("Execution plan"))
        self.plan_list = QListWidget()
        mid_layout.addWidget(self.plan_list, stretch=1)
        mid_layout.addWidget(QLabel("Milestones"))
        self.milestone_list = QListWidget()
        self.milestone_list.setMaximumHeight(100)
        mid_layout.addWidget(self.milestone_list)
        mid_layout.addWidget(QLabel("Mode stack"))
        self.stack_list = QListWidget()
        self.stack_list.setMaximumHeight(120)
        mid_layout.addWidget(self.stack_list)
        mid_layout.addWidget(QLabel("Output preview"))
        self.canvas_tabs = QTabWidget()
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setReadOnly(True)
        # Rendered HTML uses its own CSS; the font here is just the fallback.
        self.canvas_editor.setFont(QFont("Segoe UI", 11))
        self.canvas_tabs.addTab(self.canvas_editor, "Preview")
        self.walkthrough_view = QTextEdit()
        self.walkthrough_view.setReadOnly(True)
        self.canvas_tabs.addTab(self.walkthrough_view, "Walkthrough")
        mid_layout.addWidget(self.canvas_tabs, stretch=2)
        self.splitter.addWidget(middle)

        self.log_panel = ExecutionLogPanel(main_window)
        self.splitter.addWidget(self.log_panel)
        self.splitter.setSizes(SPLITTER_DEFAULTS.get("task", [280, 520, 480]))

    def _populate_plan(self, state_data: dict) -> None:
        self.plan_list.clear()
        self.milestone_list.clear()
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
            target = step.get("target_mode")
            if kind == "delegate" and target:
                item.setToolTip(f"Delegates to {target} mode | {desc}")
            else:
                item.setToolTip(desc)
            self.plan_list.addItem(item)
        approach = (state_data.get("approach_summary") or "").strip()
        if approach:
            self.plan_list.addItem(QListWidgetItem(f"📌 {approach[:120]}"))
        for m in state_data.get("milestones") or []:
            if not isinstance(m, dict):
                continue
            label = m.get("label", m.get("id", "milestone"))
            status = m.get("status", "pending")
            self.milestone_list.addItem(QListWidgetItem(f"{label} ({status})"))

    def show_walkthrough_if_present(self) -> None:
        if not self._worker:
            return
        try:
            from agent.core.task_artifacts import walkthrough_md_path
            from agent.gui.markdown_utils import escape_markdown_for_qt

            path = walkthrough_md_path(self._worker.task_name, self._worker.mode.lower())
            if path.exists():
                self.walkthrough_view.setMarkdown(
                    escape_markdown_for_qt(path.read_text(encoding="utf-8"))
                )
                self.canvas_tabs.setCurrentWidget(self.walkthrough_view)
        except Exception:
            pass

    def _populate_mode_stack(self, parent_task_id: str) -> None:
        self.stack_list.clear()
        if not parent_task_id:
            self.stack_list.addItem("(no delegations yet)")
            return
        try:
            from agent.core import load_delegation_stack

            stack = load_delegation_stack(parent_task_id)
        except Exception:
            stack = []
        if not stack:
            self.stack_list.addItem("(no delegations yet)")
            return
        for entry in stack:
            icon = "✓" if entry.status == "completed" else "○"
            wall = entry.metrics.get("wall_time_s", "?")
            self.stack_list.addItem(
                QListWidgetItem(
                    f"{icon} {entry.mode} · {entry.status} · {wall}s · {entry.delegation_id}"
                )
            )
            tip = entry.summary[:300] if entry.summary else entry.ledger_path
            self.stack_list.item(self.stack_list.count() - 1).setToolTip(tip)

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
            parent_id = self._worker.task_name if self._worker else ""
            self._populate_mode_stack(parent_id)
            ledger_html = render_step_ledger_html(state_data)
            # Right panel: keep the state tracker HTML for existing tests.
            self.log_panel.set_state_html(ledger_html)
            # Center canvas: match the redesigned wireframe (state / step ledger).
            self.canvas_editor.setHtml(ledger_html)
        except Exception:
            self.log_panel.set_state_html(
                "<p style='color: #e74c3c;'>Error reading ledger state.</p>"
            )
