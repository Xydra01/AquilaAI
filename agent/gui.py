import sys
import re
import threading
import json
import os
import time
import glob
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QComboBox,
    QStackedWidget,
    QInputDialog,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from file_parser import attachment_dialog_filter, process_local_attachments
from gui_formatting import (
    format_assistant_message_html,
    format_attachment_notice_html,
    format_character_message_html,
    format_sleep_cycle_html,
    format_system_message_html,
    format_user_message_html,
)
from gui_pages import (
    ChatPage,
    CharacterPage,
    LearnPage,
    CodeIdePage,
    ResearchPage,
    StubModePage,
    TaskPage,
    WritingPage,
    BaseModePage,
    HomePage,
)
from gui_theme import main_window_stylesheet
from gui_modes import WORKSPACE_MODE_FLAGS, workspace_label_for_default_mode

# Import Aquila's Brain and Tools
from main import get_agent, get_active_instance_id, initiate_sleep_cycle
from workspace_paths import agent_data_path, ensure_repo_cwd
from instance_registry import get_instance
from tool_library import agent_tools

MODE_FLAGS = WORKSPACE_MODE_FLAGS


class AgentWorker(QThread):
    ledger_signal = Signal(str)
    finished_signal = Signal(str)
    ask_user_signal = Signal(str)

    def __init__(
        self,
        task_name,
        prompt,
        mode,
        attached_chunks=None,
        attached_images=None,
        chat_history=None,
        instance_id=None,
        persona_id=None,
        persona_research_lore: bool = False,
        learn_syllabus_web: bool = False,
        course_id: str | None = None,
        archive_id: str | None = None,
        archive_title: str = "",
        node_id: str = "root",
    ):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode
        self.attached_chunks = attached_chunks or []
        self.attached_images = attached_images or []
        self.model_user_content = prompt
        self.chat_history = chat_history or []
        self.instance_id = instance_id or get_active_instance_id()
        self.persona_id = persona_id
        self.persona_research_lore = persona_research_lore
        self.learn_syllabus_web = learn_syllabus_web
        self.course_id = course_id
        self.archive_id = archive_id
        self.archive_title = archive_title
        self.node_id = node_id
        self.cancel_flag = False
        self.user_reply = ""
        self.reply_event = threading.Event()

    def _ask_user_bridge(self, question: str) -> str:
        self.reply_event.clear()
        self.ask_user_signal.emit(question)
        self.reply_event.wait()
        return self.user_reply

    def run(self):
        agent_tools.USER_INPUT_CALLBACK = self._ask_user_bridge
        from instance_registry import set_active_instance_id

        set_active_instance_id(self.instance_id)
        agent = get_agent(self.instance_id)
        try:
            if self.mode.lower() == "chat":
                from main import format_attachment_context

                attachment_block = format_attachment_context(self.attached_chunks)
                self.model_user_content = (
                    f"{self.prompt}{attachment_block}" if attachment_block else self.prompt
                )
                generator = agent.run_chat(
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    image_payloads=self.attached_images,
                    text_chunks=self.attached_chunks,
                    stream=True,
                )
                full_text = ""
                for chunk in generator:
                    if self.cancel_flag:
                        break
                    token = chunk.get("message", {}).get("content", "")
                    full_text += token
                    self.ledger_signal.emit(token)
                self.finished_signal.emit(full_text)
            elif self.mode.lower() == "character":
                from main import format_attachment_context
                from persona_registry import get_persona

                persona = get_persona(self.instance_id, self.persona_id or "")
                if not persona:
                    self.finished_signal.emit("❌ Error: Persona not found.")
                    return
                attachment_block = format_attachment_context(self.attached_chunks)
                self.model_user_content = (
                    f"{self.prompt}{attachment_block}" if attachment_block else self.prompt
                )
                generator = agent.run_character_chat(
                    persona,
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    image_payloads=self.attached_images,
                    text_chunks=self.attached_chunks,
                    stream=True,
                )
                full_text = ""
                for chunk in generator:
                    if self.cancel_flag:
                        break
                    token = chunk.get("message", {}).get("content", "")
                    full_text += token
                    self.ledger_signal.emit(token)
                self.finished_signal.emit(full_text)
            elif self.mode.lower() == "learn_tutor":
                generator = agent.run_learn_tutor_chat(
                    self.course_id or "",
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    node_id=self.node_id or "root",
                    text_chunks=self.attached_chunks,
                    stream=True,
                )
                full_text = ""
                for chunk in generator:
                    if self.cancel_flag:
                        break
                    token = chunk.get("message", {}).get("content", "")
                    full_text += token
                    self.ledger_signal.emit(token)
                self.finished_signal.emit(full_text)
            elif self.mode.lower() == "learn_archive_chat":
                generator = agent.run_learn_archive_chat(
                    self.archive_id or "",
                    self.archive_title or "Archive",
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    text_chunks=self.attached_chunks,
                    stream=True,
                )
                full_text = ""
                for chunk in generator:
                    if self.cancel_flag:
                        break
                    token = chunk.get("message", {}).get("content", "")
                    full_text += token
                    self.ledger_signal.emit(token)
                self.finished_signal.emit(full_text)
            else:
                res = agent.run_unified_task(
                    self.task_name,
                    self.prompt,
                    self.mode,
                    ui_callback=self.ledger_signal.emit,
                    cancel_check=lambda: self.cancel_flag,
                    text_chunks=self.attached_chunks,
                    image_payloads=self.attached_images,
                    persona_research_lore=self.persona_research_lore,
                    learn_syllabus_web=self.learn_syllabus_web,
                )
                self.finished_signal.emit(f"✅ Task Completed:\n{res}")
        except Exception as e:
            self.finished_signal.emit(f"❌ Error: {str(e)}")


class ChatSubcallWorker(QThread):
    """One-shot chat completion for selection edits (writing/code)."""

    finished_signal = Signal(str)

    def __init__(self, prompt: str, instance_id: str | None = None):
        super().__init__()
        self.prompt = prompt
        self.instance_id = instance_id or get_active_instance_id()

    def run(self):
        agent = get_agent(self.instance_id)
        try:
            resp = agent.run_chat(user_input=self.prompt, chat_history=[], stream=False)
            if isinstance(resp, dict):
                content = resp.get("message", {}).get("content", "") or ""
            else:
                content = str(resp)
            self.finished_signal.emit(content)
        except Exception as e:
            self.finished_signal.emit(f"❌ Error: {e}")


class SleepWorker(QThread):
    finished_signal = Signal(str)

    def run(self):
        try:
            result = initiate_sleep_cycle()
            self.finished_signal.emit(result)
        except Exception as e:
            self.finished_signal.emit(f"❌ Sleep Cycle Error: {str(e)}")


class WarmupModelWorker(QThread):
    finished_signal = Signal(bool, str)

    def run(self):
        try:
            from main import client

            ok, message = client.warmup()
            self.finished_signal.emit(ok, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class EjectModelWorker(QThread):
    finished_signal = Signal(bool, str)

    def __init__(self, *, all_loaded: bool = False, instance_id: str | None = None):
        super().__init__()
        self.all_loaded = all_loaded
        self.instance_id = instance_id

    def run(self):
        try:
            from instance_registry import set_active_instance_id
            from main import client

            if self.instance_id:
                set_active_instance_id(self.instance_id)
                profile = get_instance(self.instance_id)
                if profile and profile.ollama_model:
                    client.model_name = profile.ollama_model.strip()
            ok, message = client.eject_model(all_loaded=self.all_loaded)
            self.finished_signal.emit(ok, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class AquilaOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🦅 Aquila OS 3.4 - Instances & Workspaces")
        self.resize(1400, 800)
        self.dark_mode = False
        self._chat_streaming = False
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names: list[str] = []
        self.attached_file_paths: list[str] = []
        self._chat_history_messages = []
        self.worker = None
        self._eject_worker = None
        self.active_instance_id = get_active_instance_id()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_bar = QHBoxLayout()
        self.theme_btn = QPushButton("🌙 Toggle Dark Mode")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)
        self.home_btn = QPushButton("🏠 Home")
        self.home_btn.clicked.connect(self.show_home)
        top_bar.addWidget(self.home_btn)
        top_bar.addStretch()
        self.instance_label = QLabel()
        top_bar.addWidget(self.instance_label)
        self.sleep_btn = QPushButton("🧠 Initiate Sleep Cycle")
        self.sleep_btn.clicked.connect(self.trigger_sleep_cycle)
        top_bar.addWidget(self.sleep_btn)
        self.eject_btn = QPushButton("⏏️ Eject model")
        self.eject_btn.setToolTip(
            "Unload the configured Ollama model from VRAM (keep_alive=0). "
            "Also sends Stop if a task is running. Shift+click: unload every loaded model."
        )
        self.eject_btn.clicked.connect(self.eject_ollama_model)
        top_bar.addWidget(self.eject_btn)
        main_layout.addLayout(top_bar)

        self.main_stack = QStackedWidget()
        main_layout.addWidget(self.main_stack, stretch=1)

        self.home_page = HomePage(self)
        self.main_stack.addWidget(self.home_page)

        self.workspace_widget = QWidget()
        workspace_layout = QVBoxLayout(self.workspace_widget)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Workspace:"))
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(list(MODE_FLAGS.keys()))
        self.mode_selector.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_selector, stretch=1)
        workspace_layout.addLayout(mode_row)

        self.page_stack = QStackedWidget()
        workspace_layout.addWidget(self.page_stack, stretch=1)
        self.main_stack.addWidget(self.workspace_widget)

        self.chat_page = ChatPage(self)
        self.task_page = TaskPage(self)
        self.research_page = ResearchPage(self)
        self.writing_page = WritingPage(self)
        self.code_page = CodeIdePage(self)
        self.character_page = CharacterPage(self)
        self.learn_page = LearnPage(self)

        self._page_by_mode_label = {
            "Chat Mode": self.chat_page,
            "Autonomous Task": self.task_page,
            "Code Mode": self.code_page,
            "Writing Mode": self.writing_page,
            "Research Mode": self.research_page,
            "Character Mode": self.character_page,
            "Learn Mode": self.learn_page,
        }
        for page in (
            self.chat_page,
            self.task_page,
            self.research_page,
            self.writing_page,
            self.code_page,
            self.character_page,
            self.learn_page,
        ):
            self.page_stack.addWidget(page)

        self._update_instance_label()
        self.main_stack.setCurrentIndex(0)
        self.toggle_theme()
        self._maybe_warmup_on_start()

    def _maybe_warmup_on_start(self) -> None:
        if "pytest" in sys.modules:
            return
        raw = os.getenv("AQUILA_WARMUP_ON_START", "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return
        self._warmup_worker = WarmupModelWorker(self)
        self._warmup_worker.finished_signal.connect(self._on_startup_warmup_finished)
        self._warmup_worker.start()

    def _on_startup_warmup_finished(self, ok: bool, message: str) -> None:
        prefix = "✅" if ok else "⚠️"
        print(f"{prefix} Ollama warmup: {message}")

    def _apply_page_themes(self) -> None:
        for page in (
            self.chat_page,
            self.task_page,
            self.research_page,
            self.writing_page,
            self.code_page,
            self.character_page,
            self.learn_page,
        ):
            if hasattr(page, "refresh_theme"):
                page.refresh_theme(dark=self.dark_mode)

    @staticmethod
    def _reset_live_scroll_panels(page: BaseModePage) -> None:
        """Tail-follow on new runs; user can scroll up during execution to freeze view."""
        from gui_richtext import SmartScrollTextEdit

        for name in ("chat_history", "ledger_view"):
            widget = getattr(page, name, None)
            if isinstance(widget, SmartScrollTextEdit):
                widget.reset_scroll_follow()

    def show_home(self) -> None:
        self.main_stack.setCurrentIndex(0)
        self.home_page.refresh_list()

    def enter_workspace(self, instance_id: str) -> None:
        self.active_instance_id = instance_id
        self._update_instance_label()
        inst = get_instance(instance_id)
        if inst:
            label = workspace_label_for_default_mode(inst.default_mode)
            idx = self.mode_selector.findText(label)
            if idx >= 0:
                self.mode_selector.setCurrentIndex(idx)
            else:
                self._select_mode_for_flag(
                    inst.default_mode if inst.default_mode in MODE_FLAGS.values() else "chat"
                )
        self.main_stack.setCurrentIndex(1)
        self.chat_page.append_chat_html(
            format_system_message_html(
                f"Instance '{instance_id}' active. Select a workspace above."
            )
        )

    def _update_instance_label(self) -> None:
        inst = get_instance(self.active_instance_id)
        name = inst.display_name if inst else self.active_instance_id
        self.instance_label.setText(f"Instance: {name}")

    def _on_mode_changed(self, _index: int) -> None:
        label = self.mode_selector.currentText()
        page = self._page_by_mode_label.get(label, self.task_page)
        for i in range(self.page_stack.count()):
            if self.page_stack.widget(i) is page:
                self.page_stack.setCurrentIndex(i)
                if hasattr(page, "on_activate"):
                    page.on_activate()
                break

    def current_page(self) -> BaseModePage:
        w = self.page_stack.currentWidget()
        return w if isinstance(w, BaseModePage) else self.task_page

    def current_mode_flag(self) -> str:
        return MODE_FLAGS.get(self.mode_selector.currentText(), "autonomous")

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.setStyleSheet(main_window_stylesheet(dark=self.dark_mode))
        self._apply_page_themes()

    def run_chat_subcall(self, prompt: str, on_result) -> None:
        """Non-streaming chat for quick selection edits."""
        worker = ChatSubcallWorker(prompt, instance_id=self.active_instance_id)

        def _done(text: str) -> None:
            on_result(text)

        worker.finished_signal.connect(_done)
        worker.start()
        self._subcall_worker = worker

    def open_attachment_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Attach",
            "",
            attachment_dialog_filter(),
        )
        if file_paths:
            self.attached_chunks, self.attached_images = process_local_attachments(file_paths)
            self.attached_file_names = [Path(p).name for p in file_paths]
            self.attached_file_paths = list(file_paths)
            msg = f"Successfully attached and parsed {len(file_paths)} file(s).\n"
            msg += (
                f"Resulted in {len(self.attached_chunks)} text chunk(s) and "
                f"{len(self.attached_images)} image(s)."
            )
            QMessageBox.information(self, "Attachments Processed", msg)
            page = self.current_page()
            if hasattr(page, "attach_button"):
                page.attach_button.setText(f"📎 {len(file_paths)}")

    def trigger_sleep_cycle(self):
        page = self.current_page()
        page.append_chat_html(
            "<div style='margin-bottom: 15px; color: #9b59b6;'>"
            "<b>System:</b> 🌙 Initiating Sleep Cycle...</div>"
        )
        self.sleep_btn.setDisabled(True)
        self.sleep_worker = SleepWorker()
        self.sleep_worker.finished_signal.connect(self.sleep_finished)
        self.sleep_worker.start()

    def sleep_finished(self, result):
        self.current_page().append_chat_html(format_sleep_cycle_html(result))
        self.sleep_btn.setDisabled(False)

    def _infer_resume_mode(self, task_name: str) -> str:
        if agent_data_path("Agent-Plans", f"{task_name}.json").exists():
            return "research"
        if agent_data_path("Agent-Drafts", "active_draft_state.json").exists():
            return "writing"
        if agent_data_path("Agent-Code", "active_code_state.json").exists():
            return "code"
        return "autonomous"

    def _select_mode_for_flag(self, mode_flag: str) -> None:
        for label, flag in MODE_FLAGS.items():
            if flag == mode_flag:
                idx = self.mode_selector.findText(label)
                if idx >= 0:
                    self.mode_selector.setCurrentIndex(idx)
                return

    def resume_task_dialog(self):
        task_files = (
            glob.glob(str(agent_data_path("Agent-Tasks", "*.json")))
            + glob.glob(str(agent_data_path("Agent-Plans", "*.json")))
        )
        active_tasks = []
        for f in task_files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    state = json.load(fp)
                    if state.get("status") != "completed":
                        active_tasks.append(os.path.basename(f).replace(".json", ""))
            except Exception:
                pass
        code_buf = agent_data_path("Agent-Code", "active_code_state.json")
        if code_buf.exists():
            try:
                with open(code_buf, "r", encoding="utf-8") as cf:
                    code_state = json.load(cf)
                label = f"[code] {code_state.get('project_name', 'code_project')}"
                if label not in active_tasks:
                    active_tasks.append(label)
            except Exception:
                pass
        if not active_tasks:
            self.current_page().append_chat_html(
                "<div style='color: #7f8c8d;'><b>System:</b> No active tasks to resume.</div>"
            )
            return
        task_name, ok = QInputDialog.getItem(
            self, "Resume Task", "Select task:", active_tasks, 0, False
        )
        if not ok or not task_name:
            return
        if task_name.startswith("[code] "):
            mode_flag = "code"
            task_name = task_name.replace("[code] ", "", 1)
        else:
            mode_flag = self._infer_resume_mode(task_name)
        self._select_mode_for_flag(mode_flag)
        page = self.current_page()
        page.append_chat_html(
            f"<b>User (Resume):</b> Resuming {task_name}"
        )
        page.set_run_buttons_running(True)
        page.update_ledger("", clear=True)
        self._chat_streaming = False
        self.worker = AgentWorker(
            task_name,
            "Resume from current objective.",
            mode_flag,
            instance_id=self.active_instance_id,
        )
        self._wire_worker(self.worker, page)

    def stop_task(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_flag = True
            self.current_page().update_ledger("\n🛑 Abort signal sent...\n")
            self.current_page().set_run_buttons_running(False)

    def eject_ollama_model(self):
        """Unload Ollama model from VRAM; optional unload-all via Shift+click."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel_flag = True
            page = self.current_page()
            if hasattr(page, "update_ledger"):
                page.update_ledger("\n⏏️ Eject: stop signal sent; unloading model from VRAM...\n")
            page.set_run_buttons_running(False)

        all_loaded = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        self._eject_all_loaded = all_loaded
        self.eject_btn.setDisabled(True)
        for page in (
            self.chat_page,
            self.task_page,
            self.research_page,
            self.writing_page,
            self.code_page,
            self.character_page,
            self.learn_page,
        ):
            rail = getattr(page, "agent_rail", None) or getattr(page, "chat_rail", None)
            if rail and hasattr(rail, "eject_btn"):
                rail.eject_btn.setDisabled(True)

        self._eject_worker = EjectModelWorker(
            all_loaded=all_loaded,
            instance_id=self.active_instance_id,
        )
        self._eject_worker.finished_signal.connect(self._on_eject_finished)
        self._eject_worker.start()

    def _on_eject_finished(self, ok: bool, message: str) -> None:
        self.eject_btn.setDisabled(False)
        for page in (
            self.chat_page,
            self.task_page,
            self.research_page,
            self.writing_page,
            self.code_page,
            self.character_page,
            self.learn_page,
        ):
            for attr in ("agent_rail", "chat_rail", "tutor_rail", "archive_rail"):
                rail = getattr(page, attr, None)
                if rail and hasattr(rail, "eject_btn"):
                    rail.eject_btn.setDisabled(False)

        scope = "all loaded" if getattr(self, "_eject_all_loaded", False) else "configured model"
        html = format_system_message_html(
            f"⏏️ Eject ({scope}): {message}" if ok else f"⏏️ Eject failed: {message}"
        )
        self.current_page().append_chat_html(html)
        if not ok:
            QMessageBox.warning(self, "Eject model", message)

    def clear_chat_display(self):
        page = self.current_page()
        page.clear_chat_display()
        page.append_chat_html(
            format_system_message_html(
                "Chat view cleared; memory preserved for next message."
            )
        )

    def prompt_user_input(self, question):
        text, ok = QInputDialog.getMultiLineText(self, "Aquila Requires Input", question)
        self.worker.user_reply = text if ok and text else "User declined to answer."
        self.worker.reply_event.set()

    def execute_task(self):
        page = self.current_page()
        user_prompt = page.get_chat_input_text()
        if not user_prompt:
            return
        mode_flag = self.current_mode_flag()
        if mode_flag == "character" and isinstance(page, CharacterPage):
            if page.is_persona_build_view():
                return
            if not page.is_streaming_character_chat():
                return
        if mode_flag == "learn" and isinstance(page, LearnPage):
            if page.is_course_build_view() or page.is_archive_build_view():
                return
            if not page.is_streaming_learn_chat():
                return
        mode_selection = self.mode_selector.currentText()
        clean_prefix = re.sub(r"[^a-zA-Z0-9]", "", "_".join(user_prompt.split()[:3]).lower())
        task_name = f"{clean_prefix}_{int(time.time())}"
        display_prompt = user_prompt
        if mode_flag == "character" and isinstance(page, CharacterPage):
            pname = page._active_persona.display_name if page._active_persona else "Character"
            page.append_chat_html(
                format_character_message_html(pname, display_prompt, "user")
                + format_attachment_notice_html(
                    self.attached_file_names,
                    text_chunk_count=len(self.attached_chunks),
                    image_count=len(self.attached_images),
                )
            )
        else:
            page.append_chat_html(
                format_user_message_html(mode_selection, display_prompt)
                + format_attachment_notice_html(
                    self.attached_file_names,
                    text_chunk_count=len(self.attached_chunks),
                    image_count=len(self.attached_images),
                )
            )
        page.clear_chat_input()
        page.set_run_buttons_running(True)
        page.update_ledger("", clear=True)
        self._reset_live_scroll_panels(page)
        if hasattr(page, "on_task_started"):
            page.on_task_started()
        learn_worker_mode = mode_flag
        if mode_flag == "learn" and isinstance(page, LearnPage):
            learn_worker_mode = page.learn_chat_mode()
        self._chat_streaming = mode_flag in ("chat", "character", "learn")
        chunks = list(self.attached_chunks)
        if hasattr(page, "get_extra_text_chunks"):
            chunks.extend(page.get_extra_text_chunks())
        chat_history = self._chat_history_messages.copy()
        persona_id = None
        course_id = None
        archive_id = None
        archive_title = ""
        node_id = "root"
        if mode_flag == "character" and isinstance(page, CharacterPage):
            chat_history = page.get_persona_chat_history()
            persona_id = page.active_persona_id()
        if mode_flag == "learn" and isinstance(page, LearnPage):
            chat_history = page.get_learn_chat_history()
            course_id = page.active_course_id()
            archive_id = page.active_archive_id()
            node_id = page.active_node_id()
            if page._active_archive:
                archive_title = page._active_archive.title
        self.worker = AgentWorker(
            task_name,
            user_prompt,
            learn_worker_mode if mode_flag == "learn" else mode_flag,
            chunks,
            self.attached_images,
            chat_history=chat_history,
            instance_id=self.active_instance_id,
            persona_id=persona_id,
            course_id=course_id,
            archive_id=archive_id,
            archive_title=archive_title,
            node_id=node_id,
        )
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names = []
        self.attached_file_paths = []
        if hasattr(page, "attach_button"):
            page.attach_button.setText(
                "📎 Attach" if mode_flag in ("chat", "character", "learn") else "📎"
            )
        self._wire_worker(self.worker, page)

    def _start_character_build(
        self,
        *,
        task_name: str,
        prompt: str,
        chunks: list,
        images: list,
        page: CharacterPage,
        persona_research_lore: bool = False,
    ) -> None:
        page.set_run_buttons_running(True)
        page.update_ledger("", clear=True)
        self._chat_streaming = False
        self.worker = AgentWorker(
            task_name,
            prompt,
            "character_build",
            chunks,
            images,
            instance_id=self.active_instance_id,
            persona_research_lore=persona_research_lore,
        )
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names = []
        self.attached_file_paths = []
        self._wire_worker(self.worker, page)

    def _start_learn_syllabus_build(
        self,
        *,
        task_name: str,
        prompt: str,
        chunks: list,
        images: list,
        page: LearnPage,
        learn_syllabus_web: bool = False,
    ) -> None:
        page.set_run_buttons_running(True)
        page.update_ledger("", clear=True)
        self._chat_streaming = False
        self.worker = AgentWorker(
            task_name,
            prompt,
            "learn_syllabus_build",
            chunks,
            images,
            instance_id=self.active_instance_id,
            learn_syllabus_web=learn_syllabus_web,
        )
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names = []
        self.attached_file_paths = []
        self._wire_worker(self.worker, page)

    def _run_learn_subcall(self, prompt: str, on_done) -> None:
        """One-shot LLM call for assessment / archive generation."""
        worker = ChatSubcallWorker(prompt, instance_id=self.active_instance_id)
        worker.finished_signal.connect(on_done)
        worker.start()
        self._learn_subcall_worker = worker

    def _wire_worker(self, worker: AgentWorker, page: BaseModePage) -> None:
        page.bind_worker(worker)
        worker.ask_user_signal.connect(self.prompt_user_input)
        if self._chat_streaming:
            if hasattr(page, "begin_assistant_stream"):
                page.begin_assistant_stream()
            worker.ledger_signal.connect(page.stream_chat_token)
            worker.finished_signal.connect(self.chat_finished)
        else:
            worker.ledger_signal.connect(self.update_ledger_ui)
            worker.finished_signal.connect(self.task_finished)
        worker.start()

    def update_ledger_ui(self, text: str) -> None:
        page = self.current_page()
        page.update_ledger(text, clear=True)
        if self.worker:
            page.bind_worker(self.worker)
            page.refresh_state()

    def chat_finished(self, result: str) -> None:
        self._chat_streaming = False
        page = self.current_page()
        if hasattr(page, "finalize_streamed_message") and result:
            page.finalize_streamed_message(result)
        if result and self.worker:
            user_content = getattr(
                self.worker, "model_user_content", self.worker.prompt
            )
            if self.worker.mode.lower() == "character" and isinstance(
                page, CharacterPage
            ):
                page.persist_character_turn(user_content, result)
            elif self.worker.mode.lower() in (
                "learn_tutor",
                "learn_archive_chat",
            ) and isinstance(page, LearnPage):
                page.persist_learn_turn(user_content, result)
            else:
                self._chat_history_messages.append(
                    {"role": "user", "content": user_content}
                )
                self._chat_history_messages.append(
                    {"role": "assistant", "content": result}
                )
        self.current_page().set_run_buttons_running(False)

    def task_finished(self, result: str) -> None:
        page = self.current_page()
        page.append_chat_html(format_assistant_message_html(result))
        page.set_run_buttons_running(False)
        if hasattr(page, "on_task_finished"):
            page.on_task_finished()
        if self.worker and self.worker.mode.lower() != "chat":
            page.refresh_state()


if __name__ == "__main__":
    ensure_repo_cwd()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AquilaOS()
    window.show()
    sys.exit(app.exec())
