"""Writing workspace: compose-first settings + document library + canvas."""
from __future__ import annotations

import json
import re
import time
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
    QComboBox,
    QSpinBox,
    QRadioButton,
    QButtonGroup,
    QLineEdit,
)
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtCore import Qt

from .base import BaseModePage
from ..gui_theme import SPLITTER_DEFAULTS, mode_accent_style
from ..gui_widgets.agent_rail import AgentRail
from ..gui_widgets.execution_log_panel import ExecutionLogPanel
from ..gui_state import (
    resolve_ledger_path,
    render_step_ledger_html,
    render_writing_draft_html,
)
from agent.coding import (
    has_active_draft,
    list_writing_documents,
    load_active_draft_markdown,
    load_markdown_file,
    markdown_from_draft,
    sync_canvas_to_draft,
)
from agent.functions.writing_brief import SCOPE_PRESETS, WritingBrief, WritingScope
from agent.storage import agent_data_path, load_writing_defaults, save_writing_defaults


class WritingPage(BaseModePage):
    MODE = "writing"
    MODE_LABEL = "Writing Mode"

    _SCOPE_KEYS: list[tuple[str, WritingScope]] = [
        ("Quick edit / paragraph", "quick_edit"),
        ("Short note", "short_form"),
        ("Document", "standard"),
        ("Source summary", "from_sources"),
    ]

    def __init__(self, main_window):
        super().__init__(main_window)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Writing Workspace")
        header.setStyleSheet(mode_accent_style("writing"))
        root.addWidget(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self._build_compose()
        self._build_library()
        self._build_canvas()
        self.stack.setCurrentWidget(self.compose_widget)

    def is_compose_view(self) -> bool:
        return self.stack.currentWidget() is getattr(self, "compose_widget", None)

    def is_quick_task_view(self) -> bool:
        return self.stack.currentWidget() in (
            getattr(self, "library_widget", None),
            getattr(self, "canvas_widget", None),
        )

    def _build_compose(self) -> None:
        self.compose_widget = QWidget()
        layout = QVBoxLayout(self.compose_widget)
        top = QHBoxLayout()
        self.compose_library_btn = QPushButton("📚 Library")
        self.compose_library_btn.clicked.connect(
            lambda: self.stack.setCurrentWidget(self.library_widget)
        )
        top.addWidget(self.compose_library_btn)
        top.addStretch()
        layout.addLayout(top)

        layout.addWidget(QLabel("What should be written or revised?"))
        self.compose_description = QPlainTextEdit()
        self.compose_description.setPlaceholderText(
            "Describe the writing task — new document, revision, or source-based summary..."
        )
        self.compose_description.setMaximumHeight(120)
        layout.addWidget(self.compose_description)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Scope"))
        self.compose_scope = QComboBox()
        for label, _key in self._SCOPE_KEYS:
            self.compose_scope.addItem(label)
        self.compose_scope.currentIndexChanged.connect(self._on_scope_changed)
        row1.addWidget(self.compose_scope, stretch=1)
        row1.addWidget(QLabel("Tone"))
        self.compose_tone = QComboBox()
        for tone in ("neutral", "formal", "conversational", "technical", "custom"):
            self.compose_tone.addItem(tone.replace("_", " ").title(), tone)
        row1.addWidget(self.compose_tone)
        layout.addLayout(row1)

        self.compose_tone_custom = QLineEdit()
        self.compose_tone_custom.setPlaceholderText("Custom tone (when Tone is Custom)")
        layout.addWidget(self.compose_tone_custom)

        layout.addWidget(QLabel("Length target"))
        length_row = QHBoxLayout()
        self.length_group = QButtonGroup(self)
        self.length_words = QRadioButton("Words")
        self.length_paragraphs = QRadioButton("Paragraphs")
        self.length_sections = QRadioButton("Sections")
        self.length_flexible = QRadioButton("Flexible")
        self.length_sections.setChecked(True)
        for rb in (
            self.length_words,
            self.length_paragraphs,
            self.length_sections,
            self.length_flexible,
        ):
            self.length_group.addButton(rb)
            length_row.addWidget(rb)
        layout.addLayout(length_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target"))
        self.compose_target = QSpinBox()
        self.compose_target.setRange(1, 50000)
        self.compose_target.setValue(4)
        target_row.addWidget(self.compose_target)
        target_row.addStretch()
        layout.addLayout(target_row)

        doc_row = QHBoxLayout()
        doc_row.addWidget(QLabel("Edit existing document (optional)"))
        self.compose_target_doc = QComboBox()
        self.compose_target_doc.addItem("(New document)", "")
        for path in list_writing_documents():
            self.compose_target_doc.addItem(path.name, path.name)
        doc_row.addWidget(self.compose_target_doc, stretch=1)
        layout.addLayout(doc_row)

        attach_row = QHBoxLayout()
        self.compose_attach_btn = QPushButton("📎 Attach sources")
        self.compose_attach_btn.clicked.connect(self.main.open_attachment_dialog)
        attach_row.addWidget(self.compose_attach_btn)
        attach_row.addStretch()
        layout.addLayout(attach_row)
        self._context_attachments_label = QLabel("No attachments yet.")
        self._context_attachments_label.setWordWrap(True)
        layout.addWidget(self._context_attachments_label)

        self.compose_start_btn = QPushButton("▶️ Start writing")
        self.compose_start_btn.clicked.connect(self._start_compose_task)
        layout.addWidget(self.compose_start_btn)

        self.compose_log = ExecutionLogPanel(self.main, show_state_tracker=False)
        layout.addWidget(self.compose_log, stretch=1)
        self.stack.addWidget(self.compose_widget)

    def _build_library(self) -> None:
        self.library_widget = QWidget()
        layout = QVBoxLayout(self.library_widget)
        top = QHBoxLayout()
        self.library_compose_btn = QPushButton("← Compose")
        self.library_compose_btn.clicked.connect(
            lambda: self.stack.setCurrentWidget(self.compose_widget)
        )
        top.addWidget(self.library_compose_btn)
        top.addStretch()
        layout.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Documents (Agent-Drafts)"))
        self.doc_list = QListWidget()
        left_layout.addWidget(self.doc_list, stretch=2)
        if has_active_draft():
            left_layout.addWidget(
                QLabel("Active draft in progress (Agent-Drafts/active_draft_state.json)")
            )
        btn_row = QHBoxLayout()
        self.open_canvas_btn = QPushButton("Open in canvas")
        self.open_canvas_btn.clicked.connect(self._open_in_canvas)
        self.refresh_docs_btn = QPushButton("Refresh")
        self.refresh_docs_btn.clicked.connect(self._refresh_doc_list)
        for w in (self.open_canvas_btn, self.refresh_docs_btn):
            btn_row.addWidget(w)
        left_layout.addLayout(btn_row)

        self.home_agent_rail = AgentRail(
            self.main,
            placeholder="Quick prompt (optional)...",
            show_clear=True,
            compact_buttons=True,
        )
        split.addWidget(left)
        split.addWidget(self.home_agent_rail)
        split.setSizes(SPLITTER_DEFAULTS.get("writing", [360, 640]))
        layout.addWidget(split)
        self.stack.addWidget(self.library_widget)
        self._refresh_doc_list()

    def _on_scope_changed(self) -> None:
        idx = self.compose_scope.currentIndex()
        if idx < 0 or idx >= len(self._SCOPE_KEYS):
            return
        _label, scope = self._SCOPE_KEYS[idx]
        preset = SCOPE_PRESETS.get(scope, {})
        length_mode = preset.get("length_mode", "sections")
        if length_mode == "words":
            self.length_words.setChecked(True)
            self.compose_target.setValue(int(preset.get("target_words") or 400))
        elif length_mode == "paragraphs":
            self.length_paragraphs.setChecked(True)
            self.compose_target.setValue(int(preset.get("target_paragraphs") or 1))
        elif length_mode == "sections":
            self.length_sections.setChecked(True)
            self.compose_target.setValue(int(preset.get("target_sections") or 4))
        else:
            self.length_flexible.setChecked(True)

    def _length_mode(self) -> str:
        if self.length_words.isChecked():
            return "words"
        if self.length_paragraphs.isChecked():
            return "paragraphs"
        if self.length_sections.isChecked():
            return "sections"
        return "flexible"

    def _selected_scope(self) -> WritingScope:
        idx = self.compose_scope.currentIndex()
        if 0 <= idx < len(self._SCOPE_KEYS):
            return self._SCOPE_KEYS[idx][1]
        return "standard"

    def build_writing_brief(self) -> dict:
        scope = self._selected_scope()
        tone = self.compose_tone.currentData() or "neutral"
        length_mode = self._length_mode()
        target = self.compose_target.value()
        file_names = list(getattr(self.main, "attached_file_names", []) or [])
        has_attachments = bool(file_names) or scope == "from_sources"
        brief = WritingBrief.from_scope_preset(
            scope,
            tone=tone,
            tone_custom=self.compose_tone_custom.text().strip(),
            length_mode=length_mode,
            target_words=target if length_mode == "words" else None,
            target_paragraphs=target if length_mode == "paragraphs" else None,
            target_sections=target if length_mode == "sections" else None,
            target_document=self.compose_target_doc.currentData() or None,
            has_attachments=has_attachments,
        )
        return brief.to_plan_dict()

    def _load_compose_defaults(self) -> None:
        defaults = load_writing_defaults(self.main.active_instance_id)
        if not defaults:
            self._on_scope_changed()
            return
        scope = defaults.get("scope", "standard")
        for i, (_label, key) in enumerate(self._SCOPE_KEYS):
            if key == scope:
                self.compose_scope.setCurrentIndex(i)
                break
        tone = defaults.get("tone", "neutral")
        tone_idx = self.compose_tone.findData(tone)
        if tone_idx >= 0:
            self.compose_tone.setCurrentIndex(tone_idx)
        self.compose_tone_custom.setText(defaults.get("tone_custom", ""))
        length_mode = defaults.get("length_mode", "sections")
        {
            "words": self.length_words,
            "paragraphs": self.length_paragraphs,
            "sections": self.length_sections,
            "flexible": self.length_flexible,
        }.get(length_mode, self.length_sections).setChecked(True)
        target = defaults.get("target_value")
        if isinstance(target, int):
            self.compose_target.setValue(target)
        else:
            self._on_scope_changed()

    def _save_compose_defaults(self, brief: dict) -> None:
        save_writing_defaults(
            self.main.active_instance_id,
            {
                "scope": brief.get("scope"),
                "tone": brief.get("tone"),
                "tone_custom": brief.get("tone_custom", ""),
                "length_mode": brief.get("length_mode"),
                "target_value": (
                    brief.get("target_words")
                    or brief.get("target_paragraphs")
                    or brief.get("target_sections")
                ),
            },
        )

    def _start_compose_task(self) -> None:
        description = self.compose_description.toPlainText().strip()
        if not description:
            QMessageBox.information(self.main, "Writing", "Describe what to write first.")
            return
        brief = self.build_writing_brief()
        self._save_compose_defaults(brief)
        target_doc = brief.get("target_document")
        if target_doc:
            description = (
                f"Revise Agent-Drafts/{target_doc}. Instructions: {description}"
            )
        clean_prefix = re.sub(
            r"[^a-zA-Z0-9]", "", "_".join(description.split()[:3]).lower()
        )
        task_name = f"{clean_prefix}_{int(time.time())}"
        chunks = list(self.main.attached_chunks)
        images = list(self.main.attached_images)
        self.compose_log.update_ledger("", clear=True)
        self.main._start_writing_task(
            task_name=task_name,
            prompt=description,
            chunks=chunks,
            images=images,
            page=self,
            writing_brief=brief,
        )

    def refresh_context_pane(self) -> None:
        file_names = list(getattr(self.main, "attached_file_names", []) or [])
        chunks = getattr(self.main, "attached_chunks", []) or []
        images = getattr(self.main, "attached_images", []) or []
        if not file_names and not chunks and not images:
            self._context_attachments_label.setText("No attachments yet.")
            return
        parts: list[str] = []
        if file_names:
            names = ", ".join(file_names[:4]) + ("…" if len(file_names) > 4 else "")
            parts.append(f"{len(file_names)} file(s): {names}")
        if chunks:
            parts.append(f"{len(chunks)} text chunk(s)")
        if images:
            parts.append(f"{len(images)} image(s)")
        self._context_attachments_label.setText("📎 " + " · ".join(parts))

    def _active_rail(self) -> AgentRail | None:
        if self.stack.currentWidget() == self.library_widget and hasattr(self, "home_agent_rail"):
            return self.home_agent_rail
        if hasattr(self, "agent_rail") and self.stack.currentWidget() == self.canvas_widget:
            return self.agent_rail
        return None

    def _build_canvas(self) -> None:
        self.canvas_widget = QWidget()
        layout = QVBoxLayout(self.canvas_widget)
        top = QHBoxLayout()
        self.back_home_btn = QPushButton("← Compose")
        self.back_home_btn.clicked.connect(
            lambda: self.stack.setCurrentWidget(self.compose_widget)
        )
        self.save_draft_btn = QPushButton("Sync to draft buffer")
        self.save_draft_btn.clicked.connect(self._sync_draft)
        self.quick_edit_btn = QPushButton("Edit selection (chat)")
        self.quick_edit_btn.clicked.connect(self._quick_edit_selection)
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
        self.outline_list = QListWidget()
        self.outline_list.setMinimumWidth(150)
        split.addWidget(self.outline_list)

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
            compact_buttons=True,
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
        split.setSizes([200, 700, 380])
        layout.addWidget(split)
        self.stack.addWidget(self.canvas_widget)
        self._open_path: Path | None = None

    def _refresh_doc_list(self) -> None:
        self.doc_list.clear()
        current_doc = self.compose_target_doc.currentData() if hasattr(self, "compose_target_doc") else ""
        if hasattr(self, "compose_target_doc"):
            self.compose_target_doc.clear()
            self.compose_target_doc.addItem("(New document)", "")
        for path in list_writing_documents():
            self.doc_list.addItem(QListWidgetItem(path.name))
            if hasattr(self, "compose_target_doc"):
                self.compose_target_doc.addItem(path.name, path.name)
        if hasattr(self, "compose_target_doc") and current_doc:
            idx = self.compose_target_doc.findData(current_doc)
            if idx >= 0:
                self.compose_target_doc.setCurrentIndex(idx)

    def _selected_doc_path(self) -> Path | None:
        item = self.doc_list.currentItem()
        if not item:
            return None
        return agent_data_path("Agent-Drafts", item.text())

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
        draft_path = agent_data_path("Agent-Drafts", "active_draft_state.json")
        if draft_path.exists():
            try:
                with open(draft_path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                self.preview_view.setHtml(render_writing_draft_html(state_data))
                return
            except Exception:
                pass

        text = self.canvas_editor.toPlainText()
        html = markdown.markdown(text, extensions=["fenced_code", "tables"])
        self.preview_view.setHtml(html)

        self.outline_list.clear()
        for line in text.splitlines():
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                heading = line.lstrip("#").strip()
                indent = "  " * (level - 1)
                self.outline_list.addItem(f"{indent}{heading}")

    def _sync_draft(self) -> None:
        msg = sync_canvas_to_draft(self.canvas_editor.toPlainText())
        self._update_preview()
        QMessageBox.information(self.main, "Writing", msg)

    def _run_structural_task(self) -> None:
        text = self.canvas_task_input.text().strip()
        if not text:
            return
        brief = WritingBrief.from_scope_preset("quick_edit").to_plan_dict()
        self.main._start_writing_task(
            task_name=f"revise_{int(time.time())}",
            prompt=text,
            chunks=list(self.main.attached_chunks),
            images=list(self.main.attached_images),
            page=self,
            writing_brief=brief,
        )

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
        self._load_compose_defaults()
        self._refresh_doc_list()
        self.refresh_context_pane()

    def on_task_started(self) -> None:
        if self.stack.currentWidget() == self.canvas_widget:
            self.preview_tabs.setCurrentWidget(self.log_panel)

    def on_task_finished(self) -> None:
        self._refresh_doc_list()
        if self.stack.currentWidget() == self.canvas_widget:
            self.refresh_state()

    def append_chat_html(self, html: str) -> None:
        if self.is_compose_view() and hasattr(self, "compose_log"):
            return
        rail = self._active_rail()
        if rail:
            rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        if self.is_compose_view():
            if hasattr(self, "compose_log"):
                self.compose_log.update_ledger("", clear=True)
            return
        rail = self._active_rail()
        if rail:
            rail.clear_chat_display()

    def get_chat_input_text(self) -> str:
        if self.stack.currentWidget() == self.canvas_widget and self.canvas_task_input.text().strip():
            return self.canvas_task_input.text().strip()
        rail = self._active_rail()
        if rail:
            return rail.get_chat_input_text()
        return ""

    def clear_chat_input(self) -> None:
        rail = self._active_rail()
        if rail:
            rail.clear_chat_input()
        if hasattr(self, "canvas_task_input"):
            self.canvas_task_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        if hasattr(self, "compose_start_btn"):
            self.compose_start_btn.setDisabled(running)
        for rail in (getattr(self, "home_agent_rail", None), getattr(self, "agent_rail", None)):
            if rail:
                rail.set_run_buttons_running(running)
        if hasattr(self, "canvas_run_btn"):
            self.canvas_run_btn.setDisabled(running)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        if self.is_compose_view() and hasattr(self, "compose_log"):
            self.compose_log.update_ledger(text, clear=clear)
            return
        if hasattr(self, "log_panel"):
            self.log_panel.update_ledger(text, clear=clear)

    def begin_assistant_stream(self) -> None:
        if self.is_compose_view():
            return
        rail = self._active_rail()
        if rail:
            rail.begin_assistant_stream()

    def finalize_streamed_message(self, raw_text: str) -> None:
        if self.is_compose_view():
            return
        rail = self._active_rail()
        if rail:
            rail.finalize_streamed_message(raw_text)

    def stream_chat_token(self, token: str) -> None:
        if self.is_compose_view():
            return
        rail = self._active_rail()
        if rail:
            rail.stream_chat_token(token)

    def stream_thinking_token(self, token: str) -> None:
        if self.is_compose_view():
            return
        rail = self._active_rail()
        if rail:
            rail.stream_thinking_token(token)

    def on_thinking_source(self, source: str) -> None:
        if self.is_compose_view():
            return
        rail = self._active_rail()
        if rail:
            rail.set_thinking_from_content(source == "content")

    @property
    def attach_button(self):
        if self.is_compose_view():
            return self.compose_attach_btn
        rail = self._active_rail()
        return rail.attach_button if rail else None

    @property
    def chat_history(self):
        rail = self._active_rail()
        return rail.chat_history if rail else None

    @property
    def ledger_view(self):
        if self.is_compose_view() and hasattr(self, "compose_log"):
            return self.compose_log.ledger_view
        return self.log_panel.ledger_view if hasattr(self, "log_panel") else None

    def refresh_theme(self, *, dark: bool) -> None:
        for panel in (
            getattr(self, "compose_log", None),
            getattr(self, "log_panel", None),
        ):
            if panel:
                panel.refresh_theme(dark=dark)
        for rail in (getattr(self, "home_agent_rail", None), getattr(self, "agent_rail", None)):
            if rail:
                rail.refresh_theme(dark=dark)

    def refresh_state(self) -> None:
        log = self.compose_log if self.is_compose_view() else getattr(self, "log_panel", None)
        if not self._worker or not log:
            return
        state_path = resolve_ledger_path("writing", self._worker.task_name)
        draft_path = agent_data_path("Agent-Drafts", "active_draft_state.json")
        if draft_path.exists():
            try:
                with open(draft_path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                log.set_state_html(render_writing_draft_html(state_data))
                if self.stack.currentWidget() == self.canvas_widget:
                    self.canvas_editor.setPlainText(markdown_from_draft(state_data))
                    self._update_preview()
            except Exception:
                pass
        elif state_path and state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                log.set_state_html(render_step_ledger_html(state_data))
            except Exception:
                log.set_state_html(
                    "<p style='color: #e74c3c;'>Error reading writing task state.</p>"
                )
