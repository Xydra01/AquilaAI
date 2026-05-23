"""Research workspace: SearXNG search, reader, human journal, agent rail."""
from __future__ import annotations

import json

import requests
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLineEdit,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QTextEdit,
    QCheckBox,
    QWidget,
)
from PySide6.QtCore import Qt

from gui_pages.base import BaseModePage
from gui_theme import SPLITTER_DEFAULTS, mode_accent_style
from gui_widgets.agent_rail import AgentRail
from gui_widgets.execution_log_panel import ExecutionLogPanel
from gui_state import resolve_ledger_path, render_step_ledger_html
from research_journal import format_journal_context, load_journal, save_journal
from web_search_query import clean_research_query


class ResearchPage(BaseModePage):
    MODE = "research"
    MODE_LABEL = "Research Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Research Workspace")
        header.setStyleSheet(mode_accent_style("research"))
        layout.addWidget(header)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        self.agent_rail = AgentRail(main_window, placeholder="Research objective...")
        self.splitter.addWidget(self.agent_rail)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search via SearXNG (localhost:8080)...")
        self.search_input.returnPressed.connect(self._run_search)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._run_search)
        search_row.addWidget(self.search_input)
        search_row.addWidget(self.search_btn)
        center_layout.addLayout(search_row)
        self.search_status = QLabel("")
        self.search_status.setStyleSheet("color: #7f8c8d; font-size: 9pt;")
        center_layout.addWidget(self.search_status)

        self.desk_tabs = QTabWidget()
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._open_result)
        self.desk_tabs.addTab(self.results_list, "Results")
        self.reader_view = QTextEdit()
        self.reader_view.setReadOnly(True)
        self.desk_tabs.addTab(self.reader_view, "Reader")
        center_layout.addWidget(self.desk_tabs)
        self.splitter.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Human journal"))
        self.journal_editor = QTextEdit()
        self.journal_editor.setPlaceholderText("Notes for your research session...")
        right_layout.addWidget(self.journal_editor, stretch=2)
        journal_btns = QHBoxLayout()
        self.save_journal_btn = QPushButton("Save journal")
        self.save_journal_btn.clicked.connect(self._save_journal)
        self.include_journal_cb = QCheckBox("Include in next run")
        self.include_journal_cb.setChecked(True)
        journal_btns.addWidget(self.save_journal_btn)
        journal_btns.addWidget(self.include_journal_cb)
        right_layout.addLayout(journal_btns)
        self.log_panel = ExecutionLogPanel(main_window)
        right_layout.addWidget(self.log_panel, stretch=3)
        self.splitter.addWidget(right)
        sizes = SPLITTER_DEFAULTS.get("research", [320, 520, 420])
        self.splitter.setSizes(sizes)
        self._load_journal()

    def _instance_id(self) -> str:
        return getattr(self.main, "active_instance_id", "default")

    def _load_journal(self) -> None:
        self.journal_editor.setPlainText(load_journal(self._instance_id()))

    def _save_journal(self) -> None:
        save_journal(self._instance_id(), self.journal_editor.toPlainText())
        self.search_status.setText("Journal saved.")

    def _run_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return
        clean_query, note = clean_research_query(query.replace('"', "").replace("'", ""))
        self.results_list.clear()
        self.search_status.setText("Searching...")
        try:
            resp = requests.get(
                "http://localhost:8080/search",
                params={
                    "q": clean_query,
                    "format": "json",
                    "engines": "google,bing,duckduckgo,wikipedia",
                },
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:12]
            if not results:
                self.search_status.setText("No results. Is SearXNG running? (docker compose up -d)")
                return
            for r in results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = (r.get("content") or "")[:200]
                item = QListWidgetItem(f"{title}\n{url}")
                item.setData(Qt.UserRole, {"url": url, "title": title, "snippet": snippet})
                self.results_list.addItem(item)
            status = f"{len(results)} result(s)"
            if note:
                status += f" ({note})"
            self.search_status.setText(status)
        except Exception as exc:
            self.search_status.setText(f"Search failed: {exc}")

    def _open_result(self, item: QListWidgetItem) -> None:
        meta = item.data(Qt.UserRole) or {}
        url = meta.get("url", "")
        title = meta.get("title", "")
        snippet = meta.get("snippet", "")
        body = f"<h3>{title}</h3><p><a href='{url}'>{url}</a></p><p>{snippet}</p>"
        body += "<p><i>Full fetch: use agent read_webpage during a research run.</i></p>"
        self.reader_view.setHtml(body)
        self.desk_tabs.setCurrentWidget(self.reader_view)

    def on_activate(self) -> None:
        self._load_journal()

    def get_extra_run_context(self) -> str:
        if not self.include_journal_cb.isChecked():
            return ""
        return format_journal_context(self.journal_editor.toPlainText())

    def get_extra_text_chunks(self) -> list[str]:
        ctx = self.get_extra_run_context()
        return [ctx] if ctx else []

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

    def refresh_theme(self, *, dark: bool) -> None:
        self.agent_rail.refresh_theme(dark=dark)
        self.log_panel.refresh_theme(dark=dark)

    def refresh_state(self) -> None:
        if not self._worker:
            return
        state_path = resolve_ledger_path("research", self._worker.task_name)
        if not state_path or not state_path.exists():
            self.log_panel.set_state_html(
                "<p style='color: #7f8c8d;'>No active research plan yet.</p>"
            )
            return
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            self.log_panel.set_state_html(render_step_ledger_html(state_data))
        except Exception:
            self.log_panel.set_state_html(
                "<p style='color: #e74c3c;'>Error reading research plan.</p>"
            )
