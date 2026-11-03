import os
import sys

# Add the project root and agent directory to sys.path to resolve package imports
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_agent_dir = os.path.join(_project_root, "agent")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if _agent_dir not in sys.path:
    sys.path.insert(0, _agent_dir)

import re
import threading
import json
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
from qfluentwidgets import (
    MSFluentWindow,
    NavigationItemPosition,
    FluentIcon as FIF,
    setTheme,
    Theme
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from agent.coding import attachment_dialog_filter, process_local_attachments
from agent.gui.gui_formatting import (
    format_assistant_message_html,
    format_attachment_notice_html,
    format_character_message_html,
    format_sleep_cycle_html,
    format_system_message_html,
    format_user_message_html,
)
from agent.gui.gui_pages import (
    ChatPage,
    CharacterPage,
    LearnPage,
    CodeIdePage,
    ResearchPage,
    StubModePage,
    TaskPage,
    WritingPage,
    DataPage,
    BaseModePage,
    HomePage,
    SettingsPage,
    SetupWizard,
)
from agent.gui.gui_theme import chrome_stylesheet, main_window_stylesheet
from agent.gui.gui_modes import (
    WORKSPACE_MODE_FLAGS,
    data_processing_enabled,
    workspace_label_for_default_mode,
)

# Import Aquila's Brain and Tools
from agent.core import get_agent, initiate_sleep_cycle
from agent.storage import agent_data_path, ensure_repo_cwd, get_active_instance_id
from agent.storage import get_instance
from tool_library import agent_tools

MODE_FLAGS = WORKSPACE_MODE_FLAGS


def _suggest_followups(answer: str) -> list[str]:
    text = (answer or "").strip()
    if not text:
        return []
    lines = [ln.strip("-* \t") for ln in text.splitlines() if ln.strip()]
    key = lines[0] if lines else text
    key = re.sub(r"\s+", " ", key).strip()[:70]
    if not key:
        return []
    return [
        f"Can you expand on: {key}?",
        "Can you give a shorter summary?",
        "What should I do next?",
    ]


class AgentWorker(QThread):
    ledger_signal = Signal(str)
    thinking_signal = Signal(str)
    thinking_source_signal = Signal(str)
    status_signal = Signal(str)
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
        attachment_paths=None,
        persona_id=None,
        persona_research_lore: bool = False,
        learn_syllabus_web: bool = False,
        course_id: str | None = None,
        archive_id: str | None = None,
        archive_title: str = "",
        node_id: str = "root",
        light_web_research: bool = False,
        light_coding: bool = False,
        bounded_tools: bool = False,
        light_coding_repo: str | None = None,
        light_coding_block: str = "",
        execute_approved: bool = False,
        offline_research: bool = False,
        writing_brief: dict | None = None,
    ):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode
        self.attached_chunks = attached_chunks or []
        self.attached_images = attached_images or []
        self.attachment_paths = attachment_paths or []
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
        self.light_web_research = light_web_research
        self.light_coding = light_coding
        self.bounded_tools = bounded_tools
        self.light_coding_repo = light_coding_repo
        self.light_coding_block = light_coding_block or ""
        self.execute_approved = execute_approved
        self.offline_research = offline_research
        self.writing_brief = dict(writing_brief) if writing_brief else None
        self.cancel_flag = False
        self.user_reply = ""
        self.reply_event = threading.Event()

    def _ask_user_bridge(self, question: str) -> str:
        self.reply_event.clear()
        self.ask_user_signal.emit(question)
        self.reply_event.wait()
        return self.user_reply

    def _consume_chat_stream(self, generator) -> str:
        from agent.aquila_runtime.cpu_timeouts import chat_thinking_wait_status
        from agent.core.main import _ThinkStreamFilter
        from agent.parser import trim_degenerate_tail

        full_text = ""
        acc_thinking = ""
        last_status_at = 0.0
        for chunk in generator:
            if self.cancel_flag:
                try:
                    close_fn = getattr(generator, "close", None)
                    if callable(close_fn):
                        close_fn()
                except Exception:
                    pass
                break
            msg = chunk.get("message", {}) or {}
            status = msg.get("status") or ""
            if status:
                self.status_signal.emit(str(status))
            think_tok = msg.get("thinking") or ""
            token = msg.get("content") or ""
            if msg.get("thinking_source") == "content":
                self.thinking_source_signal.emit("content")
            if think_tok:
                acc_thinking += think_tok
                self.thinking_signal.emit(think_tok)
                now = time.time()
                if now - last_status_at > 8.0:
                    self.status_signal.emit(chat_thinking_wait_status())
                    last_status_at = now
            if token:
                full_text += token
                self.ledger_signal.emit(token)
        if not full_text.strip() and acc_thinking.strip():
            tail = _ThinkStreamFilter.extract_trailing_answer(acc_thinking)
            if tail:
                full_text = tail
                self.ledger_signal.emit(tail)
            elif acc_thinking.strip():
                full_text = acc_thinking.strip()
                self.ledger_signal.emit(full_text)
        return trim_degenerate_tail(full_text)

    def run(self):
        agent_tools.USER_INPUT_CALLBACK = self._ask_user_bridge
        from agent.storage import set_active_instance_id

        set_active_instance_id(self.instance_id)
        is_chat_like = self.mode.lower() in (
            "chat",
            "character",
            "learn_tutor",
            "learn_archive_chat",
        )
        if is_chat_like:
            self.status_signal.emit("Preparing agent…")
        agent = get_agent(self.instance_id)
        from agent.core import apply_runtime_settings

        apply_runtime_settings(agent.client, instance_id=self.instance_id)
        try:
            if self.mode.lower() == "chat":
                from agent.aquila_runtime.cpu_timeouts import (
                    apply_cpu_friendly_settings,
                    chat_loading_status,
                )
                from agent.core import format_attachment_context

                apply_cpu_friendly_settings()
                self.status_signal.emit(chat_loading_status())

                # Explicit warmup (same as Settings) so chat hits Ollama visibly
                # and failures surface in the chat rail instead of hanging silently.
                model = getattr(agent.client, "model_name", "") or "?"
                base = getattr(agent.client, "base_url", "") or "?"
                self.status_signal.emit(f"Warming up {model} at {base}…")
                warm_ok, warm_msg = agent.client.ensure_warmup()
                if not warm_ok:
                    self.finished_signal.emit(f"❌ {warm_msg}")
                    return
                self.status_signal.emit(f"✅ {warm_msg}")
                self.status_signal.emit("Contacting engine…")

                attachment_block = format_attachment_context(self.attached_chunks)
                self.model_user_content = (
                    f"{self.prompt}{attachment_block}" if attachment_block else self.prompt
                )
                # Prefer full light-research gathering over bare bounded search.
                # Bounded tools alone = search snippets only; with light research
                # enabled, use the research (or hybrid) path that also scrapes pages.
                if self.light_web_research and self.light_coding:
                    generator = agent.run_light_hybrid_chat(
                        user_input=self.prompt,
                        chat_history=self.chat_history,
                        image_payloads=self.attached_images,
                        text_chunks=self.attached_chunks,
                        stream=True,
                        repo_root=self.light_coding_repo,
                        code_block=self.light_coding_block or None,
                        status_cb=self.status_signal.emit,
                        stop_check=lambda: self.cancel_flag,
                    )
                elif self.light_web_research:
                    generator = agent.run_light_research_chat(
                        user_input=self.prompt,
                        chat_history=self.chat_history,
                        image_payloads=self.attached_images,
                        text_chunks=self.attached_chunks,
                        stream=True,
                        status_cb=self.status_signal.emit,
                        stop_check=lambda: self.cancel_flag,
                    )
                elif self.bounded_tools:
                    generator = agent.run_bounded_tools_chat(
                        user_input=self.prompt,
                        chat_history=self.chat_history,
                        image_payloads=self.attached_images,
                        text_chunks=self.attached_chunks,
                        stream=True,
                        status_cb=self.status_signal.emit,
                        stop_check=lambda: self.cancel_flag,
                    )
                elif self.light_coding:
                    generator = agent.run_light_coding_chat(
                        user_input=self.prompt,
                        chat_history=self.chat_history,
                        image_payloads=self.attached_images,
                        text_chunks=self.attached_chunks,
                        stream=True,
                        repo_root=self.light_coding_repo,
                        code_block=self.light_coding_block or None,
                        stop_check=lambda: self.cancel_flag,
                    )
                else:
                    generator = agent.run_chat(
                        user_input=self.prompt,
                        chat_history=self.chat_history,
                        image_payloads=self.attached_images,
                        text_chunks=self.attached_chunks,
                        stream=True,
                        stop_check=lambda: self.cancel_flag,
                    )
                self.finished_signal.emit(self._consume_chat_stream(generator))
            elif self.mode.lower() == "character":
                from agent.core import format_attachment_context
                from agent.storage import get_persona

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
                self.finished_signal.emit(self._consume_chat_stream(generator))
            elif self.mode.lower() == "learn_tutor":
                generator = agent.run_learn_tutor_chat(
                    self.course_id or "",
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    node_id=self.node_id or "root",
                    text_chunks=self.attached_chunks,
                    stream=True,
                )
                self.finished_signal.emit(self._consume_chat_stream(generator))
            elif self.mode.lower() == "learn_archive_chat":
                generator = agent.run_learn_archive_chat(
                    self.archive_id or "",
                    self.archive_title or "Archive",
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    text_chunks=self.attached_chunks,
                    stream=True,
                )
                self.finished_signal.emit(self._consume_chat_stream(generator))
            elif self.mode.lower() == "data":
                if not data_processing_enabled():
                    self.finished_signal.emit(
                        "❌ Data Processing mode is disabled. Set "
                        "AQUILA_ENABLE_DATA_PROCESSING=1 in .env and restart."
                    )
                else:
                    from agent.tasks.data_processor import run_data_processing

                    run_data_processing(
                        self.prompt,
                        self.instance_id,
                        self.ledger_signal.emit,
                        cancel_check=lambda: self.cancel_flag,
                    )
                    self.finished_signal.emit("✅ Data Processing Session Ended")
            else:
                from agent.policies import set_runtime_context
                from agent.core import act_two_phase_enabled

                set_runtime_context(getattr(agent.client, "model_name", None))
                warm_ok, warm_msg = agent.client.ensure_warmup()
                self.ledger_signal.emit(
                    f"{'✅' if warm_ok else '⚠️'} Model warmup: {warm_msg}\n"
                )
                think_cb = (
                    self.thinking_signal.emit if act_two_phase_enabled() else None
                )
                from agent.core.task_artifacts import extract_plan_review_result

                if self.execute_approved:
                    res = agent.approve_and_run_task(
                        self.task_name,
                        self.prompt,
                        self.mode,
                        ui_callback=self.ledger_signal.emit,
                        cancel_check=lambda: self.cancel_flag,
                        text_chunks=self.attached_chunks,
                        image_payloads=self.attached_images,
                        attachment_paths=self.attachment_paths,
                        persona_research_lore=self.persona_research_lore,
                        learn_syllabus_web=self.learn_syllabus_web,
                        offline_research=self.offline_research,
                        writing_brief=self.writing_brief,
                        thinking_callback=think_cb,
                    )
                else:
                    res = agent.run_unified_task(
                        self.task_name,
                        self.prompt,
                        self.mode,
                        ui_callback=self.ledger_signal.emit,
                        cancel_check=lambda: self.cancel_flag,
                        text_chunks=self.attached_chunks,
                        image_payloads=self.attached_images,
                        attachment_paths=self.attachment_paths,
                        persona_research_lore=self.persona_research_lore,
                        learn_syllabus_web=self.learn_syllabus_web,
                        offline_research=self.offline_research,
                        writing_brief=self.writing_brief,
                        thinking_callback=think_cb,
                    )
                text = res if isinstance(res, str) else str(res)
                plan_review = extract_plan_review_result(text)
                if plan_review:
                    self.finished_signal.emit(plan_review)
                elif text and not text.startswith(("✅ Task Completed:", "❌", "🛑")):
                    text = f"✅ Task Completed:\n{text}"
                    self.finished_signal.emit(text)
                else:
                    self.finished_signal.emit(text)
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

    def __init__(self, instance_id: str | None = None):
        super().__init__()
        self.instance_id = instance_id

    def run(self):
        try:
            from agent.core import apply_runtime_settings, get_agent

            agent = get_agent(self.instance_id)
            apply_runtime_settings(agent.client, instance_id=self.instance_id)
            ok, message = agent.client.ensure_warmup()
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
            from agent.storage import set_active_instance_id
            from agent.core import client

            if self.instance_id:
                set_active_instance_id(self.instance_id)
                profile = get_instance(self.instance_id)
                if profile and profile.ollama_base_url:
                    client.configure(base_url=profile.ollama_base_url.strip())
                if profile and profile.ollama_model:
                    client.configure(model_name=profile.ollama_model.strip())
            ok, message = client.eject_model(all_loaded=self.all_loaded)
            self.finished_signal.emit(ok, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class AquilaOS(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🦅 Aquila OS 3.5 - Instances & Workspaces")
        self.resize(1400, 800)
        self.dark_mode = False
        setTheme(Theme.DARK if self.dark_mode else Theme.LIGHT)
        self._chat_streaming = False
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names: list[str] = []
        self.attached_file_paths: list[str] = []
        self._chat_history_messages = []
        self.worker = None
        self._eject_worker = None
        self.active_instance_id = get_active_instance_id()
        self._last_mode_flag = "chat"

        # Add top bar buttons to the custom title bar
        self.theme_btn = QPushButton("🌙 Theme")
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.sleep_btn = QPushButton("🧠 Sleep")
        self.sleep_btn.clicked.connect(self.trigger_sleep_cycle)
        self.eject_btn = QPushButton("⏏️ Eject")
        self.eject_btn.setToolTip("Unload model from VRAM")
        self.eject_btn.clicked.connect(self.eject_ollama_model)
        self.instance_label = QLabel()
        self.instance_label.setObjectName("instanceLabel")

        # Insert them into the TitleBar layout
        tb_layout = self.titleBar.layout()
        tb_layout.insertWidget(2, self.theme_btn)
        tb_layout.insertWidget(3, self.sleep_btn)
        tb_layout.insertWidget(4, self.eject_btn)
        tb_layout.insertWidget(5, self.instance_label)
        tb_layout.insertSpacing(6, 20)

        # Initialize pages
        self.home_page = HomePage(self)
        self.home_page.setObjectName("homePage")
        self.addSubInterface(self.home_page, FIF.HOME, "Home")

        self.chat_page = ChatPage(self)
        self.chat_page.setObjectName("chatPage")
        self.addSubInterface(self.chat_page, FIF.CHAT, "Chat Mode")

        self.task_page = TaskPage(self)
        self.task_page.setObjectName("taskPage")
        self.addSubInterface(self.task_page, FIF.CALENDAR, "Autonomous Task")

        self.data_page = None
        if data_processing_enabled():
            self.data_page = DataPage(self)
            self.data_page.setObjectName("dataPage")
            self.addSubInterface(self.data_page, FIF.FOLDER, "Data Processing")

        self.code_page = CodeIdePage(self)
        self.code_page.setObjectName("codePage")
        self.addSubInterface(self.code_page, FIF.DEVELOPER_TOOLS, "Code Mode")

        self.writing_page = WritingPage(self)
        self.writing_page.setObjectName("writingPage")
        self.addSubInterface(self.writing_page, FIF.EDIT, "Writing Mode")

        self.research_page = ResearchPage(self)
        self.research_page.setObjectName("researchPage")
        self.addSubInterface(self.research_page, FIF.SEARCH, "Research Mode")

        self.character_page = CharacterPage(self)
        self.character_page.setObjectName("characterPage")
        self.addSubInterface(self.character_page, FIF.PEOPLE, "Character Mode")

        self.learn_page = LearnPage(self)
        self.learn_page.setObjectName("learnPage")
        self.addSubInterface(self.learn_page, FIF.EDUCATION, "Learn Mode")

        self.settings_page = SettingsPage(self)
        self.settings_page.setObjectName("settingsPage")
        self.settings_page.settings_applied.connect(self._update_instance_label)
        self.addSubInterface(self.settings_page, FIF.SETTING, "Settings", position=NavigationItemPosition.BOTTOM)

        self._page_by_mode_label = {
            "Chat Mode": self.chat_page,
            "Autonomous Task": self.task_page,
            "Code Mode": self.code_page,
            "Writing Mode": self.writing_page,
            "Research Mode": self.research_page,
            "Character Mode": self.character_page,
            "Learn Mode": self.learn_page,
        }
        if self.data_page is not None:
            self._page_by_mode_label["Data Processing"] = self.data_page

        self.stackedWidget.currentChanged.connect(self._on_navigation_changed)

        self._update_instance_label()
        self.switchTo(self.home_page)
        self.toggle_theme()
        self._maybe_warmup_on_start()

    def _refresh_attachment_previews(self, page: BaseModePage | None = None) -> None:
        """Best-effort refresh for attachment hint UI elements."""
        page = page or self.current_page()
        if not page:
            return
        for attr in ("agent_rail", "chat_rail", "tutor_rail", "archive_rail"):
            rail = getattr(page, attr, None)
            if rail is not None and hasattr(rail, "refresh_attachment_preview"):
                rail.refresh_attachment_preview()
        if hasattr(page, "refresh_context_pane"):
            try:
                page.refresh_context_pane()
            except Exception:
                pass

    def _maybe_warmup_on_start(self) -> None:
        if "pytest" in sys.modules:
            return
        raw = os.getenv("AQUILA_WARMUP_ON_START", "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return
        self._warmup_worker = WarmupModelWorker(self.active_instance_id)
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
            self.settings_page,
        ):
            if hasattr(page, "refresh_theme"):
                page.refresh_theme(dark=self.dark_mode)

    @staticmethod
    def _reset_live_scroll_panels(page: BaseModePage) -> None:
        """Tail-follow on new runs; user can scroll up during execution to freeze view."""
        from agent.gui.gui_richtext import SmartScrollTextEdit

        for name in ("chat_history", "ledger_view"):
            widget = getattr(page, name, None)
            if isinstance(widget, SmartScrollTextEdit):
                widget.reset_scroll_follow()

    def show_home(self) -> None:
        self.switchTo(self.home_page)
        self.home_page.refresh_list()

    def show_settings(self) -> None:
        self.switchTo(self.settings_page)

    def enter_workspace(self, instance_id: str, *, mode_label: str | None = None) -> None:
        from agent.storage import set_active_instance_id

        set_active_instance_id(instance_id)
        self.active_instance_id = instance_id
        self._update_instance_label()
        inst = get_instance(instance_id)
        target_label = mode_label
        if not target_label and inst:
            target_label = workspace_label_for_default_mode(inst.default_mode)
        if target_label:
            page = self._page_by_mode_label.get(target_label, self.chat_page)
            self.switchTo(page)
            if hasattr(self, "mode_selector"):
                idx = self.mode_selector.findText(target_label)
                if idx >= 0:
                    self.mode_selector.setCurrentIndex(idx)
        else:
            self.switchTo(self.chat_page)
        if mode_label:
            return
        page = self.current_page()
        if not hasattr(page, "append_chat_html"):
            return
        name = inst.display_name if inst else instance_id
        page.append_chat_html(
            format_system_message_html(
                f"Instance '{name}' ready — choose a mode from the sidebar "
                "(e.g. Chat Mode)."
            )
        )

    def _update_instance_label(self) -> None:
        inst = get_instance(self.active_instance_id)
        name = inst.display_name if inst else self.active_instance_id
        from agent.core import client

        host = client.base_url.replace("http://", "").replace("https://", "")
        self.instance_label.setText(f"Instance: {name} | {client.model_name} @ {host}")

    def _on_navigation_changed(self, index: int) -> None:
        widget = self.stackedWidget.widget(index)
        if hasattr(widget, "on_activate"):
            widget.on_activate()

    def current_page(self):
        return self.stackedWidget.currentWidget()

    def current_mode_flag(self) -> str:
        widget = self.current_page()
        for label, page in self._page_by_mode_label.items():
            if page is widget:
                return MODE_FLAGS.get(label, "autonomous")
        return "autonomous"

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        setTheme(Theme.DARK if self.dark_mode else Theme.LIGHT)
        self.stackedWidget.setStyleSheet(main_window_stylesheet(dark=self.dark_mode))
        self.instance_label.setStyleSheet("color: #E0E0E0;" if self.dark_mode else "color: #2D3748;")
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(chrome_stylesheet(dark=self.dark_mode))
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
            self._refresh_attachment_previews(page)

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
                page = self._page_by_mode_label.get(label, self.task_page)
                self.switchTo(page)
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
        at_files: list[str] = []
        if self.current_mode_flag() == "chat":
            from agent.core.chat_context import parse_at_context

            cleaned_prompt, at_files, _at_urls = parse_at_context(user_prompt, os.getcwd())
            user_prompt = cleaned_prompt
            if at_files:
                extra_chunks, extra_images = process_local_attachments(at_files)
                self.attached_chunks.extend(extra_chunks)
                self.attached_images.extend(extra_images)
                self.attached_file_paths.extend(at_files)
                self.attached_file_names.extend([Path(p).name for p in at_files])
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
        if mode_flag == "writing" and isinstance(page, WritingPage):
            if page.is_compose_view():
                return
            if not page.is_quick_task_view():
                return
        if mode_flag == "code":
            from agent.policies.model_tiers import check_code_model

            model_check = check_code_model(surface="gui")
            if not model_check.ok:
                QMessageBox.warning(
                    self,
                    "Code Mode — model not supported",
                    model_check.message,
                )
                return
        if mode_flag == "chat" and isinstance(page, ChatPage):
            if page.light_coding_enabled and not page.light_coding_repo_path:
                QMessageBox.warning(
                    self,
                    "Light coding",
                    "Select a repository (Open repo… or Use Code IDE project) before sending.",
                )
                return
        mode_selection = ""
        for label, page_obj in self._page_by_mode_label.items():
            if page_obj is page:
                mode_selection = label
                break
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
        if mode_flag == "chat" and hasattr(page, "set_followup_chips"):
            try:
                page.set_followup_chips([])
            except Exception:
                pass
        page.set_run_buttons_running(True)
        if mode_flag == "chat":
            from agent.aquila_runtime.cpu_timeouts import (
                apply_cpu_friendly_settings,
                chat_working_status,
            )

            apply_cpu_friendly_settings()
            page.append_chat_html(
                format_system_message_html(chat_working_status())
            )
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
        if mode_flag == "chat" and isinstance(page, ChatPage):
            chat_history = page.active_thread_history()
        light_web_research = (
            mode_flag == "chat"
            and isinstance(page, ChatPage)
            and page.light_web_research_enabled
        )
        light_coding = (
            mode_flag == "chat"
            and isinstance(page, ChatPage)
            and page.light_coding_enabled
        )
        bounded_tools = (
            mode_flag == "chat"
            and isinstance(page, ChatPage)
            and getattr(page, "bounded_tools_enabled", False)
        )
        light_coding_repo = None
        light_coding_block = ""
        if light_coding and isinstance(page, ChatPage):
            page.append_chat_html(
                format_system_message_html("Indexing codebase…")
            )
            light_coding_repo = page.light_coding_repo_path
            light_coding_block, _stats = page.ensure_light_coding_context(user_prompt)
        if light_web_research:
            page.append_chat_html(
                format_system_message_html("Searching the web…")
            )
        offline_research = (
            mode_flag == "research"
            and hasattr(page, "is_offline_research")
            and page.is_offline_research()
        )
        if offline_research:
            page.append_chat_html(
                format_system_message_html(
                    "📎 Offline research — using attachments and journal only (no web)."
                )
            )
        self.worker = AgentWorker(
            task_name,
            user_prompt,
            learn_worker_mode if mode_flag == "learn" else mode_flag,
            chunks,
            self.attached_images,
            chat_history=chat_history,
            attachment_paths=list(self.attached_file_paths),
            instance_id=self.active_instance_id,
            persona_id=persona_id,
            course_id=course_id,
            archive_id=archive_id,
            archive_title=archive_title,
            node_id=node_id,
            light_web_research=light_web_research,
            light_coding=light_coding,
            bounded_tools=bounded_tools,
            light_coding_repo=light_coding_repo,
            light_coding_block=light_coding_block,
            offline_research=offline_research,
        )
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names = []
        self.attached_file_paths = []
        if hasattr(page, "attach_button"):
            page.attach_button.setText(
                "📎 Attach"
                if mode_flag in ("chat", "character", "learn", "writing", "research")
                else "📎"
            )
        self._refresh_attachment_previews(page)
        self._wire_worker(self.worker, page)

    def _start_writing_task(
        self,
        *,
        task_name: str,
        prompt: str,
        chunks: list,
        images: list,
        page: "WritingPage",
        writing_brief: dict | None = None,
    ) -> None:
        page.set_run_buttons_running(True)
        page.update_ledger("", clear=True)
        self._chat_streaming = False
        self.worker = AgentWorker(
            task_name,
            prompt,
            "writing",
            chunks,
            images,
            attachment_paths=list(self.attached_file_paths),
            instance_id=self.active_instance_id,
            writing_brief=writing_brief,
        )
        self.attached_chunks = []
        self.attached_images = []
        self.attached_file_names = []
        self.attached_file_paths = []
        self._refresh_attachment_previews(page)
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
        self._refresh_attachment_previews(page)
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
        self._refresh_attachment_previews(page)
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
        worker.status_signal.connect(
            lambda msg: page.append_chat_html(format_system_message_html(msg))
        )
        if self._chat_streaming:
            if hasattr(page, "begin_assistant_stream"):
                page.begin_assistant_stream()
            worker.ledger_signal.connect(page.stream_chat_token)
            if hasattr(page, "stream_thinking_token"):
                worker.thinking_signal.connect(page.stream_thinking_token)
            if hasattr(page, "on_thinking_source"):
                worker.thinking_source_signal.connect(page.on_thinking_source)
            worker.finished_signal.connect(self.chat_finished)
        else:
            worker.ledger_signal.connect(self.update_ledger_ui)
            if hasattr(page, "stream_thinking_token"):
                worker.thinking_signal.connect(page.stream_thinking_token)
            if hasattr(page, "on_thinking_source"):
                worker.thinking_source_signal.connect(page.on_thinking_source)
            worker.finished_signal.connect(self.task_finished)
        worker.start()

    def update_ledger_ui(self, text: str) -> None:
        page = self.current_page()
        page.update_ledger(text, clear=True)
        if self.worker:
            page.bind_worker(self.worker)
            page.refresh_state()

    def chat_finished(self, result: str) -> None:
        from agent.parser import trim_degenerate_tail

        self._chat_streaming = False
        page = self.current_page()
        text = trim_degenerate_tail(result) if result else ""
        if text.startswith("❌"):
            page.append_chat_html(format_system_message_html(text))
        elif hasattr(page, "finalize_streamed_message"):
            if text:
                page.finalize_streamed_message(text)
            elif not bool(page.chat_history.property("_stream_has_shell")):
                thinking_text = ""
                rail = getattr(page, "agent_rail", None)
                if rail and hasattr(rail, "thinking_view"):
                    thinking_text = rail.thinking_view.toPlainText().strip()
                if thinking_text:
                    page.finalize_streamed_message(thinking_text)
                else:
                    page.append_chat_html(
                        format_system_message_html(
                            "No response from the model. On CPU this can mean the request "
                            "timed out — try a shorter message or check Settings → AI Engine."
                        )
                    )
        if text and self.worker and not text.startswith("❌"):
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
                if self.worker.mode.lower() == "chat" and isinstance(page, ChatPage):
                    self._chat_history_messages = page.persist_thread_turn(user_content, text)
                else:
                    self._chat_history_messages.append(
                        {"role": "user", "content": user_content}
                    )
                    self._chat_history_messages.append(
                        {"role": "assistant", "content": text}
                    )
            if self.worker.mode.lower() == "chat":
                followups = _suggest_followups(text)
                if followups:
                    if hasattr(page, "set_followup_chips"):
                        page.set_followup_chips(followups)
        self.current_page().set_run_buttons_running(False)

    def task_finished(self, result: str) -> None:
        from agent.core.task_artifacts import extract_plan_review_result

        page = self.current_page()
        worker_mode = (getattr(self.worker, "mode", "") or "").strip().lower()
        # Phase 3: code mode never opens plan review (code_agent has no plan).
        if worker_mode == "code":
            plan_result = None
        else:
            plan_result = extract_plan_review_result(result)
        if plan_result:
            parts = plan_result.split("|", 2)
            task_name = parts[1] if len(parts) > 1 else getattr(self.worker, "task_name", "")
            mode = parts[2] if len(parts) > 2 else getattr(self.worker, "mode", "task")
            prompt = getattr(self.worker, "prompt", "")
            chunks = list(getattr(self.worker, "attached_chunks", []) or [])
            images = list(getattr(self.worker, "attached_images", []) or [])
            self._pending_plan_review = {
                "task_name": task_name,
                "mode": mode,
                "prompt": prompt,
                "chunks": chunks,
                "images": images,
                "persona_research_lore": getattr(self.worker, "persona_research_lore", False),
                "learn_syllabus_web": getattr(self.worker, "learn_syllabus_web", False),
                "offline_research": getattr(self.worker, "offline_research", False),
            }
            page.append_chat_html(
                format_system_message_html(
                    "📋 Plan ready — review in the dialog, then approve to run."
                )
            )
            page.set_run_buttons_running(False)
            page.refresh_state()
            if hasattr(page, "desk_tabs") and hasattr(page, "plan_view"):
                page.desk_tabs.setCurrentWidget(page.plan_view)
            self._open_plan_review_dialog(page)
            return
        if result.startswith("✅") or result.startswith("🛑"):
            page.append_chat_html(format_assistant_message_html(result))
        else:
            page.append_chat_html(format_assistant_message_html(f"✅ Task Completed:\n{result}"))
        page.set_run_buttons_running(False)
        if hasattr(page, "on_task_finished"):
            page.on_task_finished()
        if self.worker and self.worker.mode.lower() != "chat":
            page.refresh_state()
            if hasattr(page, "show_walkthrough_if_present"):
                page.show_walkthrough_if_present()

    def _open_plan_review_dialog(self, page) -> None:
        pending = getattr(self, "_pending_plan_review", None) or {}
        if (pending.get("mode") or "").strip().lower() == "code":
            self._pending_plan_review = None
            return
        from agent.gui.gui_widgets.plan_review_dialog import PlanReviewDialog

        dlg = PlanReviewDialog(
            self,
            task_name=pending.get("task_name", ""),
            mode=pending.get("mode", "task"),
            user_request=pending.get("prompt", ""),
        )
        dlg.approved.connect(lambda: self._run_approved_plan(page, pending))
        dlg.revise_requested.connect(lambda fb: self._revise_plan(page, pending, fb))
        dlg.exec()

    def _run_approved_plan(self, page, pending: dict) -> None:
        page.set_run_buttons_running(True)
        self.worker = AgentWorker(
            pending["task_name"],
            pending["prompt"],
            pending["mode"],
            pending.get("chunks"),
            pending.get("images"),
            instance_id=self.active_instance_id,
            persona_research_lore=pending.get("persona_research_lore", False),
            learn_syllabus_web=pending.get("learn_syllabus_web", False),
            offline_research=pending.get("offline_research", False),
            execute_approved=True,
        )
        self._wire_worker(self.worker, page)

    def _revise_plan(self, page, pending: dict, feedback: str) -> None:
        from agent.core import get_agent

        agent = get_agent(self.active_instance_id)
        try:
            agent.revise_task_plan(
                pending["task_name"],
                pending["prompt"],
                pending["mode"],
                feedback,
                text_chunks=pending.get("chunks"),
                image_payloads=pending.get("images"),
            )
            page.append_chat_html(
                format_system_message_html("📋 Plan revised — review again.")
            )
            page.refresh_state()
            self._open_plan_review_dialog(page)
        except Exception as exc:
            page.append_chat_html(format_system_message_html(f"❌ Plan revise failed: {exc}"))
            page.set_run_buttons_running(False)


if __name__ == "__main__":
    from PySide6.QtWidgets import QWizard

    from agent.aquila_runtime.setup_gate import should_show_setup_wizard

    ensure_repo_cwd()
    try:
        from agent.aquila_runtime.cpu_timeouts import apply_cpu_friendly_settings
        from agent.aquila_runtime.search_bundle import ensure_search_support_files

        apply_cpu_friendly_settings()
        ensure_search_support_files()
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AquilaOS()
    opened_chat = False
    if should_show_setup_wizard():
        wizard = SetupWizard(window)
        if wizard.exec() != QWizard.DialogCode.Accepted:
            sys.exit(0)
        from agent.storage import ensure_default_instance, get_active_instance_id

        ensure_default_instance()
        window.enter_workspace(get_active_instance_id(), mode_label="Chat Mode")
        opened_chat = True
    window.show()
    if not opened_chat:
        window.show_home()
    sys.exit(app.exec())
