"""Character AI workspace: persona home, creation, and in-character chat."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QMessageBox,
    QWidget,
    QSplitter,
    QGroupBox,
)
from PySide6.QtCore import Qt

from gui_pages.base import BaseModePage
from gui_theme import mode_accent_style
from gui_widgets.agent_rail import AgentRail
from gui_widgets.execution_log_panel import ExecutionLogPanel
from gui_formatting import format_character_message_html
from persona_registry import (
    Persona,
    create_persona,
    delete_persona,
    get_persona,
    list_personas,
    load_chat_history,
    load_user_preferences,
    save_chat_history,
    save_user_preferences,
    sources_dir,
    count_user_turns,
)


class CharacterPage(BaseModePage):
    MODE = "character"
    MODE_LABEL = "Character Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        self._active_persona: Persona | None = None
        self._persona_history: list[dict[str, str]] = []
        self._user_turn_count = 0

        root = QVBoxLayout(self)
        header = QLabel("Character AI")
        header.setStyleSheet(mode_accent_style("character"))
        root.addWidget(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self._build_home()
        self._build_create()
        self._build_chat()
        self.stack.setCurrentWidget(self.home_widget)

    def on_activate(self) -> None:
        self._refresh_persona_list()

    def is_streaming_character_chat(self) -> bool:
        return (
            self.stack.currentWidget() is self.chat_widget
            and self._active_persona is not None
        )

    def is_persona_build_view(self) -> bool:
        return self.stack.currentWidget() is self.create_widget

    def get_chat_input_text(self) -> str:
        if self.is_streaming_character_chat():
            return self.chat_rail.chat_input.text().strip()
        return ""

    def clear_chat_input(self) -> None:
        if self.is_streaming_character_chat():
            self.chat_rail.chat_input.clear()

    def append_chat_html(self, html: str) -> None:
        if self.is_streaming_character_chat():
            self.chat_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        if self.is_streaming_character_chat():
            self.chat_rail.clear_chat_display()

    def set_run_buttons_running(self, running: bool) -> None:
        if self.is_streaming_character_chat():
            self.chat_rail.set_run_buttons_running(running)
        if self.stack.currentWidget() is self.create_widget:
            self.build_btn.setDisabled(running)
            self.create_back_btn.setDisabled(running)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        if self.stack.currentWidget() is self.create_widget:
            self.create_log.update_ledger(text, clear=clear)

    def stream_chat_token(self, token: str) -> None:
        self.chat_rail.stream_chat_token(token)

    def begin_assistant_stream(self) -> None:
        self.chat_rail.begin_assistant_stream()

    def finalize_streamed_message(self, raw_text: str) -> None:
        from gui_richtext import finalize_streamed_message as fin

        name = (
            self._active_persona.display_name
            if self._active_persona
            else "Character"
        )
        fin(
            self.chat_rail.chat_history,
            raw_text,
            html_formatter=lambda t: format_character_message_html(
                name, t, "assistant"
            ),
        )

    @property
    def attach_button(self):
        if self.is_streaming_character_chat():
            return self.chat_rail.attach_button
        if self.stack.currentWidget() is self.create_widget:
            return self.create_attach_btn
        return None

    def get_persona_chat_history(self) -> list[dict[str, str]]:
        return list(self._persona_history)

    def active_persona_id(self) -> str | None:
        return self._active_persona.id if self._active_persona else None

    def on_task_finished(self) -> None:
        if self.stack.currentWidget() is self.create_widget:
            self._refresh_persona_list()
            pid = getattr(self.main.worker, "task_name", "").replace("persona_build_", "", 1)
            persona = get_persona(self.main.active_instance_id, pid)
            if persona and persona.build_complete:
                self._open_chat(persona)
            elif persona:
                QMessageBox.warning(
                    self,
                    "Persona build",
                    "Build finished but persona may be incomplete. Check the log and retry.",
                )

    def persist_character_turn(self, user_content: str, assistant_content: str) -> None:
        if not self._active_persona or not assistant_content:
            return
        iid = self.main.active_instance_id
        pid = self._active_persona.id
        self._persona_history.append({"role": "user", "content": user_content})
        self._persona_history.append({"role": "assistant", "content": assistant_content})
        save_chat_history(iid, pid, self._persona_history)
        self._user_turn_count = count_user_turns(self._persona_history)
        if self._user_turn_count > 0 and self._user_turn_count % 10 == 0:
            self._maybe_summarize_preferences()

    def _maybe_summarize_preferences(self) -> None:
        if not self._active_persona:
            return
        snippet = "\n".join(
            f"{m['role']}: {m['content'][:400]}"
            for m in self._persona_history[-20:]
        )
        try:
            from main import get_agent

            agent = get_agent(self.main.active_instance_id)
            notes = agent.summarize_user_preferences(snippet)
            if notes.strip():
                from persona_registry import append_user_preference_note

                for line in notes.strip().splitlines():
                    line = line.lstrip("-• ").strip()
                    if line:
                        append_user_preference_note(
                            self.main.active_instance_id,
                            self._active_persona.id,
                            line,
                        )
                self.prefs_edit.setPlainText(
                    load_user_preferences(
                        self.main.active_instance_id, self._active_persona.id
                    )
                )
        except Exception:
            pass

    def _build_home(self) -> None:
        self.home_widget = QWidget()
        layout = QVBoxLayout(self.home_widget)
        layout.addWidget(QLabel("Your personas (this instance)"))
        self.persona_list = QListWidget()
        layout.addWidget(self.persona_list, stretch=2)
        row = QHBoxLayout()
        self.open_chat_btn = QPushButton("Open chat")
        self.open_chat_btn.clicked.connect(self._open_selected_chat)
        self.new_persona_btn = QPushButton("New persona")
        self.new_persona_btn.clicked.connect(self._show_create)
        self.delete_persona_btn = QPushButton("Delete")
        self.delete_persona_btn.clicked.connect(self._delete_selected)
        row.addWidget(self.open_chat_btn)
        row.addWidget(self.new_persona_btn)
        row.addWidget(self.delete_persona_btn)
        layout.addLayout(row)
        self.stack.addWidget(self.home_widget)

    def _build_create(self) -> None:
        self.create_widget = QWidget()
        layout = QVBoxLayout(self.create_widget)
        top = QHBoxLayout()
        self.create_back_btn = QPushButton("← Back")
        self.create_back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_widget))
        top.addWidget(self.create_back_btn)
        top.addStretch()
        layout.addLayout(top)
        layout.addWidget(QLabel("Display name"))
        self.create_name = QLineEdit()
        layout.addWidget(self.create_name)
        layout.addWidget(QLabel("Description (personality, setting, tone)"))
        self.create_description = QPlainTextEdit()
        self.create_description.setPlaceholderText(
            "Who is this character? What world do they live in?"
        )
        self.create_description.setMaximumHeight(120)
        layout.addWidget(self.create_description)
        self.research_lore_cb = QCheckBox("Research lore on the web (optional)")
        layout.addWidget(self.research_lore_cb)
        attach_row = QHBoxLayout()
        self.create_attach_btn = QPushButton("📎 Attach files/images")
        self.create_attach_btn.clicked.connect(self.main.open_attachment_dialog)
        attach_row.addWidget(self.create_attach_btn)
        attach_row.addStretch()
        layout.addLayout(attach_row)
        self.build_btn = QPushButton("▶️ Build persona")
        self.build_btn.clicked.connect(self._start_persona_build)
        layout.addWidget(self.build_btn)
        self.create_log = ExecutionLogPanel(self.main, show_state_tracker=False)
        layout.addWidget(self.create_log, stretch=1)
        self.stack.addWidget(self.create_widget)

    def _build_chat(self) -> None:
        self.chat_widget = QWidget()
        layout = QVBoxLayout(self.chat_widget)
        top = QHBoxLayout()
        self.chat_back_btn = QPushButton("← Personas")
        self.chat_back_btn.clicked.connect(self._back_to_home)
        self.chat_title = QLabel("Character")
        self.chat_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(self.chat_back_btn)
        top.addWidget(self.chat_title)
        top.addStretch()
        layout.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.chat_rail = AgentRail(
            self.main,
            placeholder="Talk in character...",
            show_resume=False,
            show_clear=True,
            compact_buttons=False,
        )
        self.chat_rail.run_btn.setText("▶️ Send")
        split.addWidget(self.chat_rail)

        prefs_box = QGroupBox("Notes about you")
        prefs_layout = QVBoxLayout(prefs_box)
        self.prefs_edit = QPlainTextEdit()
        self.prefs_edit.setPlaceholderText("Habits, name, boundaries — injected into character memory.")
        prefs_layout.addWidget(self.prefs_edit)
        save_prefs = QPushButton("Save preferences")
        save_prefs.clicked.connect(self._save_preferences)
        prefs_layout.addWidget(save_prefs)
        split.addWidget(prefs_box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout.addWidget(split)
        self.stack.addWidget(self.chat_widget)

    def _save_preferences(self) -> None:
        if not self._active_persona:
            return
        save_user_preferences(
            self.main.active_instance_id,
            self._active_persona.id,
            self.prefs_edit.toPlainText(),
        )
        QMessageBox.information(self, "Saved", "User preferences updated.")

    def _refresh_persona_list(self) -> None:
        self.persona_list.clear()
        for p in list_personas(self.main.active_instance_id):
            tag = f" — {p.tagline}" if p.tagline else ""
            status = "" if p.build_complete else " [building]"
            item = QListWidgetItem(f"{p.display_name}{tag}{status}")
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            self.persona_list.addItem(item)

    def _show_create(self) -> None:
        self.create_name.clear()
        self.create_description.clear()
        self.research_lore_cb.setChecked(False)
        self.create_log.update_ledger("", clear=True)
        self.stack.setCurrentWidget(self.create_widget)

    def _selected_persona_id(self) -> str | None:
        item = self.persona_list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _open_selected_chat(self) -> None:
        pid = self._selected_persona_id()
        if not pid:
            QMessageBox.information(self, "Character", "Select a persona first.")
            return
        persona = get_persona(self.main.active_instance_id, pid)
        if not persona:
            return
        if not persona.build_complete:
            QMessageBox.information(
                self,
                "Character",
                "This persona is not finished building. Create a new one or retry build.",
            )
            return
        self._open_chat(persona)

    def _open_chat(self, persona: Persona) -> None:
        self._active_persona = persona
        self.chat_title.setText(persona.display_name)
        iid = self.main.active_instance_id
        self._persona_history = load_chat_history(iid, persona.id)
        self._user_turn_count = count_user_turns(self._persona_history)
        self.prefs_edit.setPlainText(load_user_preferences(iid, persona.id))
        self.chat_rail.clear_chat_display()
        if not self._persona_history and persona.greeting:
            self.chat_rail.append_chat_html(
                format_character_message_html(
                    persona.display_name, persona.greeting, "assistant"
                )
            )
        else:
            for msg in self._persona_history:
                role = msg.get("role", "user")
                self.chat_rail.append_chat_html(
                    format_character_message_html(
                        persona.display_name, msg.get("content", ""), role
                    )
                )
        self.stack.setCurrentWidget(self.chat_widget)

    def _back_to_home(self) -> None:
        self._active_persona = None
        self._persona_history = []
        self.stack.setCurrentWidget(self.home_widget)
        self._refresh_persona_list()

    def _delete_selected(self) -> None:
        pid = self._selected_persona_id()
        if not pid:
            return
        if (
            QMessageBox.question(
                self,
                "Delete persona",
                "Delete this persona and all chat history?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        delete_persona(self.main.active_instance_id, pid)
        self._refresh_persona_list()

    def _start_persona_build(self) -> None:
        name = self.create_name.text().strip()
        desc = self.create_description.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Character", "Enter a display name.")
            return
        if not desc:
            QMessageBox.warning(self, "Character", "Enter a description.")
            return
        iid = self.main.active_instance_id
        persona = create_persona(iid, name, desc, build_complete=False)
        sources_dir(iid, persona.id).mkdir(parents=True, exist_ok=True)
        chunks = list(self.main.attached_chunks)
        images = list(self.main.attached_images)
        research = self.research_lore_cb.isChecked()
        lore_line = (
            "User enabled web research for lore — use web_search when helpful."
            if research
            else "Do NOT use web_search unless attachments are clearly insufficient."
        )
        build_steps = (
            "search (web lore) → read → synthesize initialization.md → finalize_persona"
            if research
            else "ingest (save_research_note) → synthesize initialization.md → finalize_persona"
        )
        prompt = (
            f"Build a roleplay persona.\n"
            f"Display name: {persona.display_name}\n"
            f"User description:\n{desc}\n\n"
            f"{lore_line}\n"
            f"Persona id: {persona.id}\n"
            f"Follow the build steps: {build_steps}."
        )
        task_name = f"persona_build_{persona.id}"
        from workspace_paths import agent_data_path

        stale_task = agent_data_path("Agent-Tasks", f"{task_name}.json")
        if stale_task.is_file():
            try:
                stale_task.unlink()
            except OSError:
                pass
        self.create_log.update_ledger(
            f"Building persona '{name}'…\n", clear=True
        )
        self.main._start_character_build(
            task_name=task_name,
            prompt=prompt,
            chunks=chunks,
            images=images,
            page=self,
            persona_research_lore=research,
        )
