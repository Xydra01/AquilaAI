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

from file_parser import process_local_attachments
from gui_formatting import (
    format_assistant_message_html,
    format_sleep_cycle_html,
    format_system_message_html,
    format_user_message_html,
)
from gui_pages import AutonomousPage, ChatPage, CodeIdePage, StubModePage, BaseModePage, HomePage

# Import Aquila's Brain and Tools
from main import get_agent, get_active_instance_id, initiate_sleep_cycle
from workspace_paths import agent_data_path, ensure_repo_cwd
from instance_registry import get_instance
from tool_library import agent_tools

MODE_FLAGS = {
    "Chat Mode": "chat",
    "Autonomous Task": "autonomous",
    "Code Mode": "code",
    "Writing Mode": "writing",
    "Research Mode": "research",
    "Learn Mode": "learn",
}


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
    ):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode
        self.attached_chunks = attached_chunks or []
        self.attached_images = attached_images or []
        self.chat_history = chat_history or []
        self.instance_id = instance_id or get_active_instance_id()
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
        agent = get_agent(self.instance_id)
        try:
            if self.mode.lower() == "chat":
                generator = agent.run_chat(
                    user_input=self.prompt,
                    chat_history=self.chat_history,
                    image_payloads=self.attached_images,
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
                )
                self.finished_signal.emit(f"✅ Task Completed:\n{res}")
        except Exception as e:
            self.finished_signal.emit(f"❌ Error: {str(e)}")


class SleepWorker(QThread):
    finished_signal = Signal(str)

    def run(self):
        try:
            result = initiate_sleep_cycle()
            self.finished_signal.emit(result)
        except Exception as e:
            self.finished_signal.emit(f"❌ Sleep Cycle Error: {str(e)}")


class AquilaOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🦅 Aquila OS 3.4 - Instances & Workspaces")
        self.resize(1400, 800)
        self.dark_mode = False
        self._chat_streaming = False
        self.attached_chunks = []
        self.attached_images = []
        self._chat_history_messages = []
        self.worker = None
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

        self.autonomous_page = AutonomousPage(self)
        self.chat_page = ChatPage(self)
        self.code_page = CodeIdePage(self)
        self.learn_stub = StubModePage(
            self,
            "Learn Workspace",
            "A classroom-style layout (courses, assignments, progress) is planned for Aquila 4.0.",
            "learn",
            "Learn Mode",
        )

        self._page_by_mode_label = {
            "Chat Mode": self.chat_page,
            "Autonomous Task": self.autonomous_page,
            "Code Mode": self.code_page,
            "Writing Mode": self.autonomous_page,
            "Research Mode": self.autonomous_page,
            "Learn Mode": self.learn_stub,
        }
        for page in {self.chat_page, self.autonomous_page, self.code_page, self.learn_stub}:
            self.page_stack.addWidget(page)

        self._update_instance_label()
        self.main_stack.setCurrentIndex(0)
        self.toggle_theme()

    def _apply_page_themes(self) -> None:
        for page in (self.chat_page, self.autonomous_page, self.code_page):
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
            mode_map = {
                "chat": "Chat Mode",
                "autonomous": "Autonomous Task",
                "code": "Code Mode",
                "writing": "Writing Mode",
                "research": "Research Mode",
                "learn": "Learn Mode",
            }
            label = mode_map.get(inst.default_mode, "Chat Mode")
            idx = self.mode_selector.findText(label)
            if idx >= 0:
                self.mode_selector.setCurrentIndex(idx)
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
        page = self._page_by_mode_label.get(label, self.autonomous_page)
        for i in range(self.page_stack.count()):
            if self.page_stack.widget(i) is page:
                self.page_stack.setCurrentIndex(i)
                if hasattr(page, "on_activate"):
                    page.on_activate()
                break

    def current_page(self) -> BaseModePage:
        w = self.page_stack.currentWidget()
        return w if isinstance(w, BaseModePage) else self.autonomous_page

    def current_mode_flag(self) -> str:
        return MODE_FLAGS.get(self.mode_selector.currentText(), "autonomous")

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.setStyleSheet("""
                QWidget { background-color: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI', sans-serif; }
                QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget {
                    background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px;
                    padding: 4px; selection-background-color: #264f78;
                }
                QLineEdit { padding: 6px 8px; min-height: 1.2em; }
                QPushButton {
                    background-color: #333333; border: 1px solid #3e3e42; padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #3e3e42; }
                QPushButton:disabled { color: #6e6e6e; background-color: #2a2a2a; }
                QTabWidget::pane { border: 1px solid #3e3e42; border-radius: 4px; }
                QTabBar::tab { background: #252526; padding: 6px 12px; margin-right: 2px; }
                QTabBar::tab:selected { background: #3e3e42; }
                QLabel { color: #cccccc; }
                QComboBox { background: #252526; border: 1px solid #3e3e42; padding: 4px 8px; }
                QSplitter::handle { background: #3e3e42; width: 3px; }
            """)
        else:
            self.setStyleSheet("""
                QWidget { font-family: 'Segoe UI', sans-serif; color: #1a1a1a; }
                QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget {
                    background-color: #ffffff; border: 1px solid #d0d7de; border-radius: 4px; padding: 4px;
                }
                QLineEdit { padding: 6px 8px; }
                QPushButton {
                    background-color: #f6f8fa; border: 1px solid #d0d7de; padding: 6px 12px; border-radius: 4px;
                }
                QPushButton:hover { background-color: #eaeef2; }
                QTabBar::tab { padding: 6px 12px; }
                QSplitter::handle { background: #d0d7de; width: 3px; }
            """)
        self._apply_page_themes()

    def open_attachment_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Attach",
            "",
            "All Files (*);;Images (*.png *.jpg *.jpeg *.webp *.gif);;"
            "PDFs (*.pdf);;Documents (*.txt *.py *.md *.json *.csv *.html *.htm *.docx);;"
            "Spreadsheets (*.csv *.xlsx)",
        )
        if file_paths:
            self.attached_chunks, self.attached_images = process_local_attachments(file_paths)
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
        mode_selection = self.mode_selector.currentText()
        clean_prefix = re.sub(r"[^a-zA-Z0-9]", "", "_".join(user_prompt.split()[:3]).lower())
        task_name = f"{clean_prefix}_{int(time.time())}"
        page.append_chat_html(format_user_message_html(mode_selection, user_prompt))
        page.clear_chat_input()
        page.set_run_buttons_running(True)
        page.update_ledger("", clear=True)
        self._reset_live_scroll_panels(page)
        self._chat_streaming = mode_flag == "chat"
        self.worker = AgentWorker(
            task_name,
            user_prompt,
            mode_flag,
            self.attached_chunks,
            self.attached_images,
            chat_history=self._chat_history_messages.copy(),
            instance_id=self.active_instance_id,
        )
        self.attached_chunks = []
        self.attached_images = []
        if hasattr(page, "attach_button"):
            page.attach_button.setText("📎 Attach" if mode_flag == "chat" else "📎")
        self._wire_worker(self.worker, page)

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
            self._chat_history_messages.append(
                {"role": "user", "content": self.worker.prompt}
            )
            self._chat_history_messages.append({"role": "assistant", "content": result})
        self.current_page().set_run_buttons_running(False)

    def task_finished(self, result: str) -> None:
        self.current_page().append_chat_html(format_assistant_message_html(result))
        self.current_page().set_run_buttons_running(False)
        if self.worker and self.worker.mode.lower() != "chat":
            self.current_page().refresh_state()


if __name__ == "__main__":
    ensure_repo_cwd()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AquilaOS()
    window.show()
    sys.exit(app.exec())
