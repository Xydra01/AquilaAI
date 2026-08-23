"""Chat-only workspace."""
from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QSplitter,
    QWidget,
    QToolBox,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QPlainTextEdit,
    QComboBox,
    QInputDialog,
)
from PySide6.QtCore import Qt

from .base import BaseModePage
from ..gui_theme import mode_accent_style
from ..gui_widgets.agent_rail import AgentRail
from ..gui_widgets.wrapping_layout import clear_layout, make_wrapping_row


class ChatPage(BaseModePage):
    MODE = "chat"
    MODE_LABEL = "Chat Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        self._light_coding_repo_path = ""
        self._light_coding_context_block = ""
        self._light_coding_stats: dict = {}
        self._active_thread_id = ""
        self._thread_history: list[dict[str, str]] = []

        layout = QVBoxLayout(self)
        header = QLabel("Chat Workspace")
        header.setStyleSheet(mode_accent_style("chat"))
        layout.addWidget(header)

        split = QSplitter(Qt.Horizontal)
        layout.addWidget(split, stretch=1)

        self.agent_rail = AgentRail(
            main_window,
            placeholder="Say hello or ask a question...",
            show_resume=False,
            show_clear=True,
            compact_buttons=False,
            layout_variant="bottom",
        )
        self.agent_rail.run_btn.setText("▶️ Send")
        split.addWidget(self.agent_rail)

        context_box = QToolBox()
        context_widget = QWidget()
        ctx_layout = QVBoxLayout(context_widget)
        ctx_layout.addWidget(QLabel("Context Pane"))

        thread_row = QHBoxLayout()
        self.thread_combo = QComboBox()
        self.thread_combo.currentIndexChanged.connect(self._on_thread_changed)
        thread_row.addWidget(self.thread_combo, stretch=1)
        ctx_layout.addLayout(thread_row)

        thread_btn_wrap, self.thread_btn_flow = make_wrapping_row()
        self.new_thread_btn = QPushButton("New chat")
        self.new_thread_btn.clicked.connect(self._create_new_thread)
        self.thread_btn_flow.addWidget(self.new_thread_btn)
        self.regen_btn = QPushButton("Regenerate")
        self.regen_btn.clicked.connect(self._regenerate_last_turn)
        self.thread_btn_flow.addWidget(self.regen_btn)
        self.edit_last_btn = QPushButton("Edit last")
        self.edit_last_btn.clicked.connect(self._edit_last_user_turn)
        self.thread_btn_flow.addWidget(self.edit_last_btn)
        self.fork_btn = QPushButton("Fork")
        self.fork_btn.clicked.connect(self._fork_thread)
        self.thread_btn_flow.addWidget(self.fork_btn)
        ctx_layout.addWidget(thread_btn_wrap)

        self._context_attachments_label = QLabel("No attachments yet.")
        self._context_attachments_label.setWordWrap(True)
        ctx_layout.addWidget(self._context_attachments_label)

        self.light_web_research_checkbox = QCheckBox(
            "Light web research (search + auto-scrape)"
        )
        self.light_web_research_checkbox.setToolTip(
            "Plans 1–2 focused web searches from your message (not the whole prompt), "
            "auto-scrapes top results, and reads any http(s) links you paste. "
            "Not a full Research Mode report."
        )
        ctx_layout.addWidget(self.light_web_research_checkbox)

        self.light_coding_checkbox = QCheckBox(
            "Light coding (repo snapshot)"
        )
        self.light_coding_checkbox.setToolTip(
            "Indexes a local repo (~20k token budget) and injects file context before each chat reply. "
            "Read-only; not full Code Mode."
        )
        ctx_layout.addWidget(self.light_coding_checkbox)

        self.bounded_tools_checkbox = QCheckBox("Tools (bounded)")
        self.bounded_tools_checkbox.setToolTip(
            "Run a small 1-3 iteration web-tools pass before answering."
        )
        ctx_layout.addWidget(self.bounded_tools_checkbox)

        self._followup_chips: list[QPushButton] = []
        followup_label = QLabel("Follow-ups")
        followup_label.setStyleSheet("font-size: 9.5pt; opacity: 0.9;")
        ctx_layout.addWidget(followup_label)
        self.followup_wrap, self.followup_row = make_wrapping_row()
        ctx_layout.addWidget(self.followup_wrap)

        repo_btn_wrap, self.repo_btn_flow = make_wrapping_row()
        self._open_repo_btn = QPushButton("Open repo…")
        self._open_repo_btn.clicked.connect(self._pick_repo_directory)
        self.repo_btn_flow.addWidget(self._open_repo_btn)

        self._use_code_ide_btn = QPushButton("Use Code IDE project")
        self._use_code_ide_btn.clicked.connect(self._use_code_ide_project)
        self.repo_btn_flow.addWidget(self._use_code_ide_btn)

        self._clear_repo_btn = QPushButton("Clear")
        self._clear_repo_btn.clicked.connect(self._clear_light_coding_repo)
        self.repo_btn_flow.addWidget(self._clear_repo_btn)

        self._refresh_context_btn = QPushButton("Refresh context")
        self._refresh_context_btn.clicked.connect(self._refresh_light_coding_context)
        self.repo_btn_flow.addWidget(self._refresh_context_btn)
        ctx_layout.addWidget(repo_btn_wrap)

        self._light_coding_status_label = QLabel("No repo selected.")
        self._light_coding_status_label.setWordWrap(True)
        ctx_layout.addWidget(self._light_coding_status_label)

        self._open_code_mode_btn = QPushButton("Open in Code Mode")
        self._open_code_mode_btn.clicked.connect(self._open_in_code_mode)
        self._open_code_mode_btn.setEnabled(False)
        ctx_layout.addWidget(self._open_code_mode_btn)

        ctx_layout.addStretch()

        context_box.addItem(context_widget, "Context")

        # Memory / Preferences pane
        memory_widget = QWidget()
        memory_layout = QVBoxLayout(memory_widget)
        self.memory_edit = QPlainTextEdit()
        self.memory_edit.setPlaceholderText("Notes about you and your projects (learned automatically).")
        memory_layout.addWidget(self.memory_edit)
        save_memory_btn = QPushButton("Save Memory")
        save_memory_btn.clicked.connect(self._save_chat_memory)
        memory_layout.addWidget(save_memory_btn)
        context_box.addItem(memory_widget, "Agent Memory")

        split.addWidget(context_box)
        split.setSizes([900, 350])

        self.refresh_context_pane()

    @property
    def chat_history(self):
        return self.agent_rail.chat_history

    @property
    def chat_input(self):
        return self.agent_rail.chat_input

    @property
    def attach_button(self):
        return self.agent_rail.attach_button

    @property
    def run_btn(self):
        return self.agent_rail.run_btn

    @property
    def stop_btn(self):
        return self.agent_rail.stop_btn

    @property
    def clear_chat_btn(self):
        return self.agent_rail.clear_chat_btn

    @property
    def light_web_research_enabled(self) -> bool:
        return self.light_web_research_checkbox.isChecked()

    @property
    def light_coding_enabled(self) -> bool:
        return self.light_coding_checkbox.isChecked()

    @property
    def bounded_tools_enabled(self) -> bool:
        return self.bounded_tools_checkbox.isChecked()

    def set_followup_chips(self, followups: list[str]) -> None:
        clear_layout(self.followup_row)
        self._followup_chips = []

        if not followups:
            return

        max_n = 4
        for txt in followups[:max_n]:
            btn = QPushButton(txt[:60] + ("…" if len(txt) > 60 else ""))
            btn.setToolTip(txt)
            btn.clicked.connect(lambda _checked=False, t=txt: self._on_followup_clicked(t))
            self.followup_row.addWidget(btn)
            self._followup_chips.append(btn)

    def _on_followup_clicked(self, text: str) -> None:
        # ChatPage owns its AgentRail; AquilaOS (main) does not expose agent_rail.
        self.chat_input.setText(text)
        try:
            self.chat_input.setFocus()
        except Exception:
            pass

    @property
    def light_coding_repo_path(self) -> str:
        return self._light_coding_repo_path

    @property
    def light_coding_context_block(self) -> str:
        return self._light_coding_context_block

    def set_light_coding_cache(self, block: str, stats: dict) -> None:
        self._light_coding_context_block = block or ""
        self._light_coding_stats = dict(stats or {})
        self._update_light_coding_status()

    def invalidate_light_coding_cache(self) -> None:
        from agent.coding import invalidate_session_cache

        self._light_coding_context_block = ""
        self._light_coding_stats = {}
        invalidate_session_cache()
        self._update_light_coding_status()

    def ensure_light_coding_context(self, user_input: str = "", *, force: bool = False) -> tuple[str, dict]:
        """Build or reuse cached repo snapshot."""
        from agent.coding import build_light_coding_context

        if not self._light_coding_repo_path:
            return "", {}
        if self._light_coding_context_block and not force:
            return self._light_coding_context_block, self._light_coding_stats
        block, stats = build_light_coding_context(
            self._light_coding_repo_path,
            user_input,
            force_refresh=force,
        )
        self.set_light_coding_cache(block, stats)
        return block, stats

    def _pick_repo_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open repository for light coding")
        if not path:
            return
        self._set_light_coding_repo(path)

    def _use_code_ide_project(self) -> None:
        from tool_library.code_canvas_tools import get_active_project_scope

        scope = get_active_project_scope()
        if not scope or not scope.get("root"):
            QMessageBox.information(
                self,
                "Code IDE project",
                "No active Code IDE project. Open a project in Code Mode first.",
            )
            return
        root = scope["root"]
        if not Path(root).is_dir():
            QMessageBox.warning(
                self,
                "Code IDE project",
                f"Code IDE root not found on disk: {root}",
            )
            return
        self._set_light_coding_repo(root)

    def _set_light_coding_repo(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        if resolved != self._light_coding_repo_path:
            self._light_coding_repo_path = resolved
            self.invalidate_light_coding_cache()
        self._open_code_mode_btn.setEnabled(bool(self._light_coding_repo_path))
        self._update_light_coding_status()

    def _clear_light_coding_repo(self) -> None:
        self._light_coding_repo_path = ""
        self.invalidate_light_coding_cache()
        self._open_code_mode_btn.setEnabled(False)
        self._update_light_coding_status()

    def _refresh_light_coding_context(self) -> None:
        if not self._light_coding_repo_path:
            QMessageBox.information(self, "Light coding", "Select a repo first.")
            return
        self.invalidate_light_coding_cache()
        block, stats = self.ensure_light_coding_context(force=True)
        if stats.get("error"):
            QMessageBox.warning(self, "Light coding", stats["error"])
        elif not block:
            QMessageBox.warning(self, "Light coding", "No indexable source files found.")
        else:
            self._update_light_coding_status()

    def _open_in_code_mode(self) -> None:
        path = self._light_coding_repo_path
        if not path:
            return
        from tool_library import code_canvas_tools

        name = Path(path).name or "project"
        result = code_canvas_tools.attach_existing_repo(path, name)
        idx = self.main.mode_selector.findText("Code Mode")
        if idx >= 0:
            self.main.mode_selector.setCurrentIndex(idx)
        QMessageBox.information(self, "Code Mode", result[:2000])

    def _update_light_coding_status(self) -> None:
        if not self._light_coding_repo_path:
            self._light_coding_status_label.setText("No repo selected.")
            return
        stats = self._light_coding_stats or {}
        tokens = stats.get("tokens_used", 0)
        budget = stats.get("token_budget", 20000)
        walked = stats.get("files_walked", 0)
        full_n = stats.get("files_full", 0)
        summary_n = stats.get("files_summary", 0)
        cached = " (cached)" if stats.get("cached") else ""
        short_path = self._light_coding_repo_path
        if len(short_path) > 60:
            short_path = "…" + short_path[-57:]
        self._light_coding_status_label.setText(
            f"📁 {short_path}\n"
            f"{tokens} / {budget} tokens · {walked} files walked · "
            f"{full_n} full · {summary_n} summarized{cached}"
        )

    def refresh_theme(self, *, dark: bool) -> None:
        self.agent_rail.refresh_theme(dark=dark)
        hint_color = "#7f8c8d" if not dark else "#8e8e8e"
        self._context_attachments_label.setStyleSheet(f"color: {hint_color};")
        self._light_coding_status_label.setStyleSheet(f"color: {hint_color};")

    def append_chat_html(self, html: str) -> None:
        self.agent_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        self.agent_rail.clear_chat_display()

    def get_chat_input_text(self) -> str:
        return self.agent_rail.get_chat_input_text()

    def clear_chat_input(self) -> None:
        self.agent_rail.clear_chat_input()

    def set_run_buttons_running(self, running: bool) -> None:
        self.agent_rail.set_run_buttons_running(running)

    def begin_assistant_stream(self) -> None:
        self.agent_rail.begin_assistant_stream()

    def stream_chat_token(self, token: str) -> None:
        self.agent_rail.stream_chat_token(token)

    def stream_thinking_token(self, token: str) -> None:
        self.agent_rail.stream_thinking_token(token)

    def on_thinking_source(self, source: str) -> None:
        self.agent_rail.set_thinking_from_content(source == "content")

    def finalize_streamed_message(self, raw_text: str) -> None:
        self.agent_rail.finalize_streamed_message(raw_text)

    def refresh_context_pane(self) -> None:
        """Update the collapsible right pane from the main window state."""
        file_names = list(getattr(self.main, "attached_file_names", []) or [])
        chunks = getattr(self.main, "attached_chunks", []) or []
        images = getattr(self.main, "attached_images", []) or []
        chunk_count = len(chunks)
        image_count = len(images)

        if not file_names and chunk_count == 0 and image_count == 0:
            self._context_attachments_label.setText("No attachments yet.")
        else:
            names = ", ".join(file_names[:4]) + ("…" if len(file_names) > 4 else "")
            parts: list[str] = []
            if file_names:
                parts.append(f"{len(file_names)} file(s): {names}")
            if chunk_count:
                parts.append(f"{chunk_count} text chunk(s)")
            if image_count:
                parts.append(f"{image_count} image(s)")
            self._context_attachments_label.setText("📎 " + " · ".join(parts))

        self._update_light_coding_status()

    @property
    def active_thread_id(self) -> str:
        return self._active_thread_id

    def active_thread_history(self) -> list[dict[str, str]]:
        return list(self._thread_history)

    def persist_thread_turn(self, user_content: str, assistant_content: str) -> list[dict[str, str]]:
        from agent.storage import save_thread_history

        if not self._active_thread_id:
            self._ensure_threads_loaded()
        self._thread_history = list(self._thread_history)
        self._thread_history.append({"role": "user", "content": user_content})
        self._thread_history.append({"role": "assistant", "content": assistant_content})
        save_thread_history(self.main.active_instance_id, self._active_thread_id, self._thread_history)
        self._refresh_thread_list(select_id=self._active_thread_id)
        return list(self._thread_history)

    def on_activate(self) -> None:
        from agent.storage import load_chat_memory

        iid = self.main.active_instance_id
        mem = load_chat_memory(iid)
        self.memory_edit.setPlainText(mem)
        self._ensure_threads_loaded()

    def _ensure_threads_loaded(self) -> None:
        from agent.storage import ensure_default_thread, load_thread_history

        iid = self.main.active_instance_id
        if not self._active_thread_id:
            self._active_thread_id = ensure_default_thread(iid).id
        self._thread_history = load_thread_history(iid, self._active_thread_id)
        self._refresh_thread_list(select_id=self._active_thread_id)

    def _refresh_thread_list(self, *, select_id: str | None = None) -> None:
        from agent.storage import list_threads

        iid = self.main.active_instance_id
        threads = list_threads(iid)
        self.thread_combo.blockSignals(True)
        self.thread_combo.clear()
        target = select_id or self._active_thread_id
        sel_idx = 0
        for i, t in enumerate(threads):
            self.thread_combo.addItem(t.title, t.id)
            if t.id == target:
                sel_idx = i
        if self.thread_combo.count() > 0:
            self.thread_combo.setCurrentIndex(sel_idx)
            self._active_thread_id = self.thread_combo.currentData()
        self.thread_combo.blockSignals(False)

    def _create_new_thread(self) -> None:
        from agent.storage import create_thread

        iid = self.main.active_instance_id
        t = create_thread(iid, "New chat")
        self._active_thread_id = t.id
        self._thread_history = []
        self.main._chat_history_messages = []
        self.clear_chat_display()
        self._refresh_thread_list(select_id=t.id)

    def _on_thread_changed(self, _idx: int) -> None:
        from agent.storage import load_thread_history

        tid = self.thread_combo.currentData()
        if not tid:
            return
        self._active_thread_id = str(tid)
        self._thread_history = load_thread_history(self.main.active_instance_id, self._active_thread_id)
        self.main._chat_history_messages = list(self._thread_history)

    def _regenerate_last_turn(self) -> None:
        from agent.storage import regenerate_last_turn

        if not self._active_thread_id:
            return
        hist, prompt = regenerate_last_turn(self.main.active_instance_id, self._active_thread_id)
        self._thread_history = hist
        self.main._chat_history_messages = list(hist)
        if prompt:
            self.chat_input.setText(prompt)
            self.main.run_mode_handler()
        else:
            QMessageBox.information(self, "Regenerate", "No prior user turn to regenerate.")

    def _edit_last_user_turn(self) -> None:
        from agent.storage import edit_last_user_turn

        if not self._active_thread_id:
            return
        current = ""
        for m in reversed(self._thread_history):
            if m.get("role") == "user":
                current = m.get("content", "")
                break
        if not current:
            QMessageBox.information(self, "Edit last", "No user turn found in this thread.")
            return
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Edit last user message",
            "Edit and resend from this turn:",
            current,
        )
        if not ok:
            return
        edited = edit_last_user_turn(self.main.active_instance_id, self._active_thread_id, text)
        self._thread_history = edited
        self.main._chat_history_messages = list(edited)
        self.chat_input.setText((text or "").strip())
        self.main.run_mode_handler()

    def _fork_thread(self) -> None:
        from agent.storage import fork_thread, load_thread_history

        if not self._active_thread_id:
            return
        t = fork_thread(
            self.main.active_instance_id,
            self._active_thread_id,
            title_hint="Forked chat",
        )
        self._active_thread_id = t.id
        self._thread_history = load_thread_history(self.main.active_instance_id, t.id)
        self.main._chat_history_messages = list(self._thread_history)
        self._refresh_thread_list(select_id=t.id)

    def _save_chat_memory(self) -> None:
        from agent.storage import save_chat_memory

        iid = self.main.active_instance_id
        save_chat_memory(iid, self.memory_edit.toPlainText())
        QMessageBox.information(self, "Saved", "Agent memory updated.")

    def persist_chat_turn(self, user_content: str, assistant_content: str, full_history: list) -> None:
        if not assistant_content:
            return
        from agent.storage import count_user_turns

        turn_count = count_user_turns(full_history)
        if turn_count > 0 and turn_count % 10 == 0:
            self._maybe_summarize_memory(full_history)

    def _maybe_summarize_memory(self, full_history: list) -> None:
        snippet = "\n".join(
            f"{m['role']}: {m['content'][:400]}"
            for m in full_history[-20:]
        )
        try:
            from agent.core import get_agent
            from agent.storage import load_chat_memory, save_chat_memory

            iid = self.main.active_instance_id
            agent = get_agent(iid)
            current_mem = load_chat_memory(iid)
            new_mem = agent.update_chat_memory(snippet, current_mem)
            save_chat_memory(iid, new_mem)
            self.memory_edit.setPlainText(new_mem)
        except Exception:
            pass
