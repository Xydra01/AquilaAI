"""Writing workspace: document home + markdown canvas."""
from __future__ import annotations

import json
from pathlib import Path

import markdown
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QTextEdit,
    QTabWidget,
    QInputDialog,
    QMessageBox,
    QWidget,
)
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtCore import Qt

from gui_pages.base import BaseModePage
from gui_theme import SPLITTER_DEFAULTS, mode_accent_style
from gui_widgets.agent_rail import AgentRail
from gui_widgets.execution_log_panel import ExecutionLogPanel
from gui_state import (
    resolve_ledger_path,
    render_step_ledger_html,
    render_writing_draft_html,
)
from writing_canvas import (
    has_active_draft,
    list_writing_documents,
    load_active_draft_markdown,
    load_markdown_file,
    markdown_from_draft,
    sync_canvas_to_draft,
)
from workspace_paths import agent_data_path


class WritingPage(BaseModePage):
    MODE = "writing"
    MODE_LABEL = "Writing Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Writing Workspace")
        header.setStyleSheet(mode_accent_style("writing"))
        root.addWidget(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self._build_home()
        self._build_canvas()
        self.stack.setCurrentWidget(self.home_widget)

    def _build_home(self) -> None:
        self.home_widget = QWidget()
        layout = QVBoxLayout(self.home_widget)
        layout.addWidget(QLabel("Documents (Agent-Drafts)"))
        self.doc_list = QListWidget()
        layout.addWidget(self.doc_list, stretch=2)
        if has_active_draft():
            layout.addWidget(QLabel("Active draft in progress (Agent-Drafts/active_draft_state.json)"))
        btn_row = QHBoxLayout()
        self.new_doc_btn = QPushButton("New document (agent)")
        self.new_doc_btn.clicked.connect(self._new_document)
        self.edit_doc_btn = QPushButton("Edit with agent")
        self.edit_doc_btn.clicked.connect(self._edit_document)
        self.open_canvas_btn = QPushButton("Open in canvas")
        self.open_canvas_btn.clicked.connect(self._open_in_canvas)
        self.refresh_docs_btn = QPushButton("Refresh")
        self.refresh_docs_btn.clicked.connect(self._refresh_doc_list)
        for w in (
            self.new_doc_btn,
            self.edit_doc_btn,
            self.open_canvas_btn,
            self.refresh_docs_btn,
        ):
            btn_row.addWidget(w)
        layout.addLayout(btn_row)
        creations = agent_data_path("Agent-Creations")
        if creations.exists():
            layout.addWidget(QLabel("Task summaries (Agent-Creations)"))
            self.creations_list = QListWidget()
            for p in sorted(creations.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                self.creations_list.addItem(QListWidgetItem(p.name))
            layout.addWidget(self.creations_list, stretch=1)
        else:
            self.creations_list = None
        self.stack.addWidget(self.home_widget)
        self._refresh_doc_list()

    def _build_canvas(self) -> None:
        self.canvas_widget = QWidget()
        layout = QVBoxLayout(self.canvas_widget)
        top = QHBoxLayout()
        self.back_home_btn = QPushButton("← Writing home")
        self.back_home_btn.clicked.connect(self._go_home)
        self.save_draft_btn = QPushButton("Sync to draft buffer")
        self.save_draft_btn.clicked.connect(self._sync_draft)
        self.quick_edit_btn = QPushButton("Edit selection (chat)")
        self.quick_edit_btn.clicked.connect(self._quick_edit_selection)
        from PySide6.QtWidgets import QLineEdit

        self.canvas_task_input = QLineEdit()
        self.canvas_task_input.setPlaceholderText("Revise whole doc / section (runs writing agent)...")
        self.canvas_task_input.returnPressed.connect(self._run_structural_task)
        self.canvas_run_btn = QPushButton("Run writing agent")
        self.canvas_run_btn.clicked.connect(self._run_structural_task)
        top.addWidget(self.back_home_btn)
        top.addWidget(self.save_draft_btn)
        top.addWidget(self.quick_edit_btn)
        top.addStretch()
        layout.addLayout(top)
        layout.addWidget(self.canvas_task_input)
        layout.addWidget(self.canvas_run_btn)

        split = QSplitter(Qt.Horizontal)
        self.canvas_editor = QPlainTextEdit()
        self.canvas_editor.setFont(QFont("Segoe UI", 12))
        self.canvas_editor.textChanged.connect(self._update_preview)
        split.addWidget(self.canvas_editor)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.agent_rail = AgentRail(
            self.main,
            placeholder="Writing task while in canvas...",
            show_clear=True,
        )
        right_layout.addWidget(self.agent_rail, stretch=2)
        self.preview_tabs = QTabWidget()
        self.preview_view = QTextEdit()
        self.preview_view.setReadOnly(True)
        self.preview_tabs.addTab(self.preview_view, "Preview")
        self.log_panel = ExecutionLogPanel(self.main)
        self.preview_tabs.addTab(self.log_panel, "Execution Log")
        right_layout.addWidget(self.preview_tabs, stretch=2)
        split.addWidget(right)
        split.setSizes(SPLITTER_DEFAULTS.get("writing", [280, 700, 380])[::-1][:2] or [500, 400])
        layout.addWidget(split)
        self.stack.addWidget(self.canvas_widget)
        self._open_path: Path | None = None

    def _refresh_doc_list(self) -> None:
        self.doc_list.clear()
        for path in list_writing_documents():
            self.doc_list.addItem(QListWidgetItem(path.name))

    def _selected_doc_path(self) -> Path | None:
        item = self.doc_list.currentItem()
        if not item:
            return None
        return agent_data_path("Agent-Drafts", item.text())

    def _go_home(self) -> None:
        self.stack.setCurrentWidget(self.home_widget)
        self._refresh_doc_list()

    def _open_in_canvas(self) -> None:
        path = self._selected_doc_path()
        if path and path.exists():
            self._open_path = path
            self.canvas_editor.setPlainText(load_markdown_file(path))
        elif has_active_draft():
            md = load_active_draft_markdown()
            self._open_path = None
            self.canvas_editor.setPlainText(md or "")
        else:
            QMessageBox.information(self.main, "Writing", "Select a document or start a draft.")
            return
        self._update_preview()
        self.stack.setCurrentWidget(self.canvas_widget)

    def _update_preview(self) -> None:
        text = self.canvas_editor.toPlainText()
        html = markdown.markdown(text, extensions=["fenced_code", "tables"])
        self.preview_view.setHtml(
            f"<div style='font-family: Arial; line-height: 1.6;'>{html}</div>"
        )

    def _sync_draft(self) -> None:
        msg = sync_canvas_to_draft(self.canvas_editor.toPlainText())
        self._update_preview()
        QMessageBox.information(self.main, "Writing", msg)

    def _new_document(self) -> None:
        prompt, ok = QInputDialog.getMultiLineText(
            self.main, "New document", "Describe the document to create:"
        )
        if ok and prompt.strip():
            self.main.mode_selector.setCurrentText("Writing Mode")
            self.agent_rail.chat_input.setText(f"Create a new writing document: {prompt.strip()}")
            self.stack.setCurrentWidget(self.canvas_widget)
            self.main.execute_task()

    def _edit_document(self) -> None:
        path = self._selected_doc_path()
        if not path:
            QMessageBox.information(self.main, "Writing", "Select a document first.")
            return
        prompt, ok = QInputDialog.getMultiLineText(
            self.main,
            "Edit document",
            f"How should the agent revise {path.name}?",
        )
        if ok and prompt.strip():
            self._open_in_canvas()
            self.agent_rail.chat_input.setText(
                f"Revise the writing file Agent-Drafts/{path.name}: {prompt.strip()}"
            )
            self.main.execute_task()

    def _run_structural_task(self) -> None:
        text = self.canvas_task_input.text().strip()
        if not text:
            return
        self.agent_rail.chat_input.setText(text)
        self.main.execute_task()

    def _quick_edit_selection(self) -> None:
        cursor = self.canvas_editor.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(self.main, "Writing", "Highlight text first.")
            return
        instruction, ok = QInputDialog.getMultiLineText(
            self.main, "Edit selection", "Instruction for the agent:"
        )
        if not ok or not instruction.strip():
            return
        selection = cursor.selectedText()
        self.main.run_chat_subcall(
            f"Edit the following text per instruction.\n"
            f"Instruction: {instruction.strip()}\n\n"
            f"Text:\n{selection}\n\n"
            "Return only the revised text, no preamble.",
            on_result=lambda revised: self._apply_selection_edit(cursor, revised),
        )

    def _apply_selection_edit(self, cursor: QTextCursor, revised: str) -> None:
        if not revised or not revised.strip():
            return
        cursor.insertText(revised.strip())
        self._update_preview()

    def on_activate(self) -> None:
        if self.stack.currentWidget() == self.home_widget:
            self._refresh_doc_list()

    def on_task_started(self) -> None:
        if self.stack.currentWidget() == self.canvas_widget:
            self.preview_tabs.setCurrentWidget(self.log_panel)

    def append_chat_html(self, html: str) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.clear_chat_display()

    def get_chat_input_text(self) -> str:
        if self.stack.currentWidget() == self.canvas_widget and self.canvas_task_input.text().strip():
            return self.canvas_task_input.text().strip()
        if hasattr(self, "agent_rail"):
            return self.agent_rail.get_chat_input_text()
        return ""

    def clear_chat_input(self) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.clear_chat_input()
        if hasattr(self, "canvas_task_input"):
            self.canvas_task_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.set_run_buttons_running(running)
        if hasattr(self, "canvas_run_btn"):
            self.canvas_run_btn.setDisabled(running)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        if hasattr(self, "log_panel"):
            self.log_panel.update_ledger(text, clear=clear)

    def begin_assistant_stream(self) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.begin_assistant_stream()

    def finalize_streamed_message(self, raw_text: str) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.finalize_streamed_message(raw_text)

    def stream_chat_token(self, token: str) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.stream_chat_token(token)

    @property
    def attach_button(self):
        return self.agent_rail.attach_button if hasattr(self, "agent_rail") else None

    @property
    def chat_history(self):
        return self.agent_rail.chat_history if hasattr(self, "agent_rail") else None

    @property
    def ledger_view(self):
        return self.log_panel.ledger_view if hasattr(self, "log_panel") else None

    def refresh_theme(self, *, dark: bool) -> None:
        if hasattr(self, "agent_rail"):
            self.agent_rail.refresh_theme(dark=dark)
        if hasattr(self, "log_panel"):
            self.log_panel.refresh_theme(dark=dark)

    def refresh_state(self) -> None:
        if not self._worker or not hasattr(self, "log_panel"):
            return
        state_path = resolve_ledger_path("writing", self._worker.task_name)
        draft_path = agent_data_path("Agent-Drafts", "active_draft_state.json")
        if draft_path.exists():
            try:
                with open(draft_path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                self.log_panel.set_state_html(render_writing_draft_html(state_data))
                if self.stack.currentWidget() == self.canvas_widget:
                    self.canvas_editor.setPlainText(markdown_from_draft(state_data))
                    self._update_preview()
            except Exception:
                pass
        elif state_path and state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                self.log_panel.set_state_html(render_step_ledger_html(state_data))
            except Exception:
                self.log_panel.set_state_html(
                    "<p style='color: #e74c3c;'>Error reading writing task state.</p>"
                )
