import sys
import re
import threading
import markdown
import json
import os
import datetime
import time
import glob
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox,
    QTabWidget, QInputDialog, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor, QTextCursor
from file_parser import process_local_attachments
from gui_state import (
    resolve_ledger_path,
    render_step_ledger_html,
    render_writing_draft_html,
)

# Import Aquila's Brain and Tools
from main import global_agent, initiate_sleep_cycle
from tool_library import agent_tools

# ---------------------------------------------------------
# 1. BACKGROUND THREADS (Agent & Sleep Cycle)
# ---------------------------------------------------------
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
    ):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode
        self.attached_chunks = attached_chunks or []
        self.attached_images = attached_images or []
        self.chat_history = chat_history or []
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
        try:
            if self.mode.lower() == "chat":
                generator = global_agent.run_chat(
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
                res = global_agent.run_unified_task(
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


# ---------------------------------------------------------
# 2. THE MAIN WINDOW
# ---------------------------------------------------------
class AquilaOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🦅 Aquila OS 3.2 - Desktop Canvas")
        self.resize(1400, 800)
        self.dark_mode = False
        self._chat_streaming = False

        self.attached_chunks = []
        self.attached_images = []
        self._chat_history_messages = []

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_bar = QHBoxLayout()
        self.theme_btn = QPushButton("🌙 Toggle Dark Mode")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)
        top_bar.addStretch()
        self.sleep_btn = QPushButton("🧠 Initiate Sleep Cycle")
        self.sleep_btn.clicked.connect(self.trigger_sleep_cycle)
        top_bar.addWidget(self.sleep_btn)
        main_layout.addLayout(top_bar)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)

        self.mode_selector = QComboBox()
        self.mode_selector.addItems(
            ["Chat Mode", "Autonomous Task", "Writing Mode", "Research Mode"]
        )
        left_layout.addWidget(QLabel("Operation Mode:"))
        left_layout.addWidget(self.mode_selector)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.append("<b>System:</b> Aquila OS 3.2 Online. Memory modules active.")
        left_layout.addWidget(self.chat_history)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Assign a task or say hello...")
        self.chat_input.returnPressed.connect(self.execute_task)
        left_layout.addWidget(self.chat_input)

        btn_layout = QHBoxLayout()
        self.attach_button = QPushButton("📎 Attach Files")
        self.attach_button.clicked.connect(self.open_attachment_dialog)
        btn_layout.addWidget(self.attach_button)

        self.run_btn = QPushButton("▶️ Run")
        self.run_btn.clicked.connect(self.execute_task)
        self.resume_btn = QPushButton("📂 Resume Task")
        self.resume_btn.clicked.connect(self.resume_task_dialog)
        self.stop_btn = QPushButton("🛑 Stop")
        self.stop_btn.clicked.connect(self.stop_task)
        self.stop_btn.setDisabled(True)

        self.clear_chat_btn = QPushButton("🧹 Clear Chat View")
        self.clear_chat_btn.clicked.connect(self.clear_chat_display)

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.resume_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.clear_chat_btn)
        left_layout.addLayout(btn_layout)

        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.addWidget(QLabel("📝 The Canvas"))
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setFont(QFont("Courier New", 11))
        middle_layout.addWidget(self.canvas_editor)

        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)

        self.tab_widget = QTabWidget()
        self.ledger_view = QTextEdit()
        self.ledger_view.setReadOnly(True)
        self.ledger_view.setFont(QFont("Consolas", 10))
        self.tab_widget.addTab(self.ledger_view, "Execution Log")

        self.state_view = QTextEdit()
        self.state_view.setReadOnly(True)
        self.state_view.setFont(QFont("Consolas", 10))
        self.tab_widget.addTab(self.state_view, "Task State Tracker")

        right_layout.addWidget(self.tab_widget)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.middle_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([300, 600, 500])
        self.worker = None

        self.toggle_theme()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.setStyleSheet("""
                QWidget { background-color: #1e1e1e; color: #d4d4d4; }
                QTextEdit, QLineEdit { background-color: #252526; border: 1px solid #3e3e42; }
                QPushButton { background-color: #333333; border: 1px solid #3e3e42; padding: 5px; }
                QPushButton:hover { background-color: #3e3e42; }
                QTabWidget::pane { border: 1px solid #3e3e42; }
                QTabBar::tab { background: #252526; padding: 5px 10px; }
                QTabBar::tab:selected { background: #3e3e42; }
            """)
            self.ledger_view.setStyleSheet("color: #4CAF50;")
        else:
            self.setStyleSheet("")
            self.ledger_view.setStyleSheet("color: #006400;")

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
            self.attach_button.setText(f"📎 {len(file_paths)} Attached")

    def trigger_sleep_cycle(self):
        self.chat_history.append(
            "<div style='margin-bottom: 15px; color: #9b59b6;'>"
            "<b>System:</b> 🌙 Initiating Sleep Cycle. Consolidating memories...</div>"
        )
        self.sleep_btn.setDisabled(True)
        self.run_btn.setDisabled(True)
        self.resume_btn.setDisabled(True)

        self.sleep_worker = SleepWorker()
        self.sleep_worker.finished_signal.connect(self.sleep_finished)
        self.sleep_worker.start()

    def sleep_finished(self, result):
        html_content = markdown.markdown(result, extensions=["fenced_code", "tables"])
        bubble = (
            f"<div style='margin-bottom: 20px; padding: 10px; border-left: 4px solid #9b59b6;'>"
            f"<b style='color: #9b59b6;'>🧠 System (Sleep Cycle):</b><br>"
            f"<div style='line-height: 1.5;'>{html_content}</div></div>"
        )
        self.chat_history.append(bubble)
        self.sleep_btn.setDisabled(False)
        self.run_btn.setDisabled(False)
        self.resume_btn.setDisabled(False)

    def _infer_resume_mode(self, task_name: str) -> str:
        if os.path.exists(f"Agent-Plans/{task_name}.json"):
            return "research"
        draft = Path("Agent-Drafts/active_draft_state.json")
        if draft.exists():
            return "writing"
        return "autonomous"

    def resume_task_dialog(self):
        task_files = glob.glob("Agent-Tasks/*.json") + glob.glob("Agent-Plans/*.json")
        active_tasks = []
        for f in task_files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    state = json.load(fp)
                    if state.get("status") != "completed":
                        active_tasks.append(os.path.basename(f).replace(".json", ""))
            except Exception:
                pass

        if not active_tasks:
            self.chat_history.append(
                "<div style='margin-bottom: 15px; color: #7f8c8d;'>"
                "<b>System:</b> No active tasks found to resume.</div>"
            )
            return

        task_name, ok = QInputDialog.getItem(
            self,
            "Resume Task",
            "Select an incomplete task to resume:",
            active_tasks,
            0,
            False,
        )

        if ok and task_name:
            mode_flag = self._infer_resume_mode(task_name)
            user_prompt = "Resume execution from the current objective."

            user_bubble = (
                f"<div style='margin-top: 15px; margin-bottom: 10px; padding: 10px; "
                f"border-left: 4px solid #e74c3c;'>"
                f"<b style='color: #e74c3c;'>👤 User (Resume Task):</b><br>"
                f"<span style='font-size: 1.05em;'>Resuming: {task_name}</span></div>"
            )
            self.chat_history.append(user_bubble)

            self.run_btn.setDisabled(True)
            self.resume_btn.setDisabled(True)
            self.stop_btn.setDisabled(False)
            self.ledger_view.clear()
            self._chat_streaming = False

            self.worker = AgentWorker(task_name, user_prompt, mode_flag)
            self.worker.ledger_signal.connect(self.update_ledger_ui)
            self.worker.ask_user_signal.connect(self.prompt_user_input)
            self.worker.finished_signal.connect(self.task_finished)
            self.worker.start()

    def stop_task(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_flag = True
            self.ledger_view.append("\n\n🛑 ABORT SIGNAL SENT. Waiting for agent to safely halt...\n")
            self.stop_btn.setDisabled(True)

    def clear_chat_display(self):
        """Clear visible chat bubbles without wiping in-memory conversation history."""
        self.chat_history.clear()
        self.chat_history.append(
            "<b>System:</b> Chat view cleared. Conversation memory is still active for the next message."
        )

    def prompt_user_input(self, question):
        text, ok = QInputDialog.getMultiLineText(self, "Aquila Requires Input", question)
        if ok and text:
            self.worker.user_reply = text
        else:
            self.worker.user_reply = "User declined to answer or cancelled."
        self.worker.reply_event.set()

    def execute_task(self):
        user_prompt = self.chat_input.text().strip()
        if not user_prompt:
            return

        mode_selection = self.mode_selector.currentText()
        if mode_selection == "Chat Mode":
            mode_flag = "chat"
        elif mode_selection == "Research Mode":
            mode_flag = "research"
        elif mode_selection == "Writing Mode":
            mode_flag = "writing"
        else:
            mode_flag = "autonomous"

        clean_prefix = re.sub(r"[^a-zA-Z0-9]", "", "_".join(user_prompt.split()[:3]).lower())
        task_name = f"{clean_prefix}_{int(time.time())}"

        user_bubble = (
            f"<div style='margin-top: 15px; margin-bottom: 10px; padding: 10px; "
            f"border-left: 4px solid #e74c3c;'>"
            f"<b style='color: #e74c3c;'>👤 User ({mode_selection}):</b><br>"
            f"<span style='font-size: 1.05em;'>{user_prompt}</span></div>"
        )
        self.chat_history.append(user_bubble)
        self.chat_input.clear()

        self.run_btn.setDisabled(True)
        self.resume_btn.setDisabled(True)
        self.stop_btn.setDisabled(False)
        self.ledger_view.clear()
        self._chat_streaming = mode_flag == "chat"

        self.worker = AgentWorker(
            task_name,
            user_prompt,
            mode_flag,
            self.attached_chunks,
            self.attached_images,
            chat_history=self._chat_history_messages.copy(),
        )

        self.attached_chunks = []
        self.attached_images = []
        self.attach_button.setText("📎 Attach Files")

        if mode_flag == "chat":
            self.chat_history.append(
                "<div style='margin-bottom: 20px; padding: 10px; border-left: 4px solid #3498db;'>"
                "<b style='color: #3498db;'>🦅 Aquila:</b><br>"
                "<span id='chat-stream-body'></span></div>"
            )
            self.worker.ledger_signal.connect(self.stream_chat_token)
            self.worker.finished_signal.connect(self.chat_finished)
        else:
            self.worker.ledger_signal.connect(self.update_ledger_ui)
            self.worker.finished_signal.connect(self.task_finished)

        self.worker.ask_user_signal.connect(self.prompt_user_input)
        self.worker.start()

    def stream_chat_token(self, token):
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.chat_history.setTextCursor(cursor)

    def chat_finished(self, result):
        """Re-enable UI after chat streaming without duplicating the response bubble."""
        self._chat_streaming = False
        if result and self.worker is not None:
            self._chat_history_messages.append(
                {"role": "user", "content": self.worker.prompt}
            )
            self._chat_history_messages.append({"role": "assistant", "content": result})
        self.run_btn.setDisabled(False)
        self.resume_btn.setDisabled(False)
        self.stop_btn.setDisabled(True)
        self.chat_input.setFocus()

    def update_ledger_ui(self, text):
        self.ledger_view.clear()
        self.ledger_view.append(text)

        if not self.worker:
            return

        self._refresh_state_tracker()

    def _refresh_state_tracker(self):
        if not self.worker:
            return

        mode = self.worker.mode.lower()
        state_path = resolve_ledger_path(mode, self.worker.task_name)

        if not state_path or not state_path.exists():
            self.state_view.setHtml(
                "<p style='color: #7f8c8d;'>No active ledger file yet.</p>"
            )
            return

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            if mode == "writing" or (
                state_path.name == "active_draft_state.json"
            ):
                html_state = render_writing_draft_html(state_data)
                self.state_view.setHtml(html_state)

                title = state_data.get("title", "Draft")
                canvas_text = f"# {title}\n\n"
                for sec in state_data.get("sections", []):
                    canvas_text += f"## {sec.get('header', '')}\n{sec.get('content', '')}\n\n"
                canvas_html = markdown.markdown(
                    canvas_text, extensions=["fenced_code", "tables"]
                )
                self.canvas_editor.setHtml(
                    f"<div style='font-family: Arial, sans-serif; line-height: 1.6;'>"
                    f"{canvas_html}</div>"
                )
            else:
                self.state_view.setHtml(render_step_ledger_html(state_data))

        except Exception:
            self.state_view.setHtml(
                "<p style='color: #e74c3c;'>Error reading ledger state.</p>"
            )

    def task_finished(self, result):
        html_content = markdown.markdown(result, extensions=["fenced_code", "tables"])
        agent_bubble = (
            f"<div style='margin-bottom: 20px; padding: 10px; border-left: 4px solid #3498db;'>"
            f"<b style='color: #3498db;'>🦅 Aquila:</b><br>"
            f"<div style='line-height: 1.5;'>{html_content}</div></div>"
        )
        self.chat_history.append(agent_bubble)

        self.run_btn.setDisabled(False)
        self.resume_btn.setDisabled(False)
        self.stop_btn.setDisabled(True)
        self.chat_input.setFocus()

        if self.worker and self.worker.mode.lower() != "chat":
            self._refresh_state_tracker()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AquilaOS()
    window.show()
    sys.exit(app.exec())
