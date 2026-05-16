import sys
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
    QTabWidget, QInputDialog, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor
from file_parser import process_local_attachments

# Import Aquila's Brain and Tools
from main import global_agent, initiate_sleep_cycle
from tool_library import agent_tools
from prompts import get_chat_prompt

# ---------------------------------------------------------
# 1. BACKGROUND THREADS (Agent & Sleep Cycle)
# ---------------------------------------------------------
class AgentWorker(QThread):
    ledger_signal = Signal(str)
    finished_signal = Signal(str)
    ask_user_signal = Signal(str)

    def __init__(self, task_name, prompt, mode, attached_chunks=None, attached_images=None):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode
        self.attached_chunks = attached_chunks or []
        self.attached_images = attached_images or []
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
            if self.mode == "chat":
                self.ledger_signal.emit("Bypassing execution engine. Processing conversational chat...")
                
                current_time = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
                facts = global_agent.memory.get_all_facts()
                episodic_memories = global_agent.memory.recall_experiences(self.prompt)
                
                system_prompt = get_chat_prompt(facts, episodic_memories)
                
                # Inject file contexts for Chat Mode
                augmented_prompt = self.prompt
                if self.attached_chunks:
                    augmented_prompt += f"\n\n[USER ATTACHED FILE CONTEXT (Part 1/{len(self.attached_chunks)})]:\n" + self.attached_chunks[0]
                    if len(self.attached_chunks) > 1:
                        augmented_prompt += "\n\n(System Note: Additional file chunks exist. The OS will automatically rotate them into your context if you request the next chunk.)"

                message_dict = {"role": "user", "content": augmented_prompt}
                if self.attached_images:
                    message_dict["images"] = self.attached_images

                history = [{"role": "system", "content": system_prompt}]
                history.append(message_dict)
                
                response = global_agent.client.chat(history)
                self.finished_signal.emit(f"✅ {response}")
            else:
                result = global_agent.run_unified_task(
                    task_name=self.task_name,
                    user_request=self.prompt,
                    mode=self.mode,
                    ui_callback=self.ledger_signal.emit,
                    cancel_check=lambda: self.cancel_flag,
                    text_chunks=self.attached_chunks,
                    image_payloads=self.attached_images
                )
                self.finished_signal.emit(f"✅ Task Completed:\n{result}")
        except Exception as e:
            self.finished_signal.emit(f"❌ Engine Error: {str(e)}")

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

        # Initialize Session State Variables for UI
        self.attached_chunks = []
        self.attached_images = []

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- SYSTEM TOP BAR ---
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

        # --- LEFT PANEL ---
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Chat Mode", "Autonomous Task", "Writing Mode", "Research Mode"])
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

        # Execution Buttons
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

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.resume_btn)
        btn_layout.addWidget(self.stop_btn)
        left_layout.addLayout(btn_layout)

        # --- MIDDLE PANEL ---
        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.addWidget(QLabel("📝 The Canvas"))
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setFont(QFont("Courier New", 11))
        middle_layout.addWidget(self.canvas_editor)

        # --- RIGHT PANEL ---
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

    # --- ATTACHMENT DIALOG LOGIC ---
    def open_attachment_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Files to Attach", 
            "", 
            "All Files (*);;Images (*.png *.jpg *.jpeg);;PDFs (*.pdf);;Text Files (*.txt *.py *.md *.json)"
        )
        
        if file_paths:
            self.attached_chunks, self.attached_images = process_local_attachments(file_paths)
            
            msg = f"Successfully attached and parsed {len(file_paths)} file(s).\n"
            msg += f"Resulted in {len(self.attached_chunks)} text chunk(s) and {len(self.attached_images)} image(s)."
            QMessageBox.information(self, "Attachments Processed", msg)
            
            self.attach_button.setText(f"📎 {len(file_paths)} Attached")

    # --- SLEEP CYCLE LOGIC ---
    def trigger_sleep_cycle(self):
        self.chat_history.append("<div style='margin-bottom: 15px; color: #9b59b6;'><b>System:</b> 🌙 Initiating Sleep Cycle. Consolidating memories...</div>")
        self.sleep_btn.setDisabled(True)
        self.run_btn.setDisabled(True)
        self.resume_btn.setDisabled(True)
        
        self.sleep_worker = SleepWorker()
        self.sleep_worker.finished_signal.connect(self.sleep_finished)
        self.sleep_worker.start()

    def sleep_finished(self, result):
        html_content = markdown.markdown(result, extensions=['fenced_code', 'tables'])
        bubble = f"<div style='margin-bottom: 20px; padding: 10px; border-left: 4px solid #9b59b6; background-color: rgba(155, 89, 182, 0.05);'><b style='color: #9b59b6;'>🧠 System (Sleep Cycle):</b><br><div style='line-height: 1.5;'>{html_content}</div></div>"
        
        self.chat_history.append(bubble)
        self.sleep_btn.setDisabled(False)
        self.run_btn.setDisabled(False)
        self.resume_btn.setDisabled(False)

    # --- RESUME TASK LOGIC ---
    def resume_task_dialog(self):
        # Scan for active tasks
        task_files = glob.glob("Agent-Tasks/*.json") + glob.glob("Agent-Plans/*.json")
        active_tasks = []
        for f in task_files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    state = json.load(fp)
                    if state.get("status") != "completed":
                        active_tasks.append(os.path.basename(f).replace('.json', ''))
            except Exception:
                pass
                
        if not active_tasks:
            self.chat_history.append("<div style='margin-bottom: 15px; color: #7f8c8d;'><b>System:</b> No active tasks found to resume.</div>")
            return
            
        task_name, ok = QInputDialog.getItem(self, "Resume Task", "Select an incomplete task to resume:", active_tasks, 0, False)
        
        if ok and task_name:
            if os.path.exists(f"Agent-Plans/{task_name}.json"):
                mode_flag = "research"
            else:
                mode_flag = "autonomous"
                
            user_prompt = "Resume execution from the current objective."
            
            user_bubble = f"<div style='margin-top: 15px; margin-bottom: 10px; padding: 10px; border-left: 4px solid #e74c3c; background-color: rgba(231, 76, 60, 0.1);'><b style='color: #e74c3c;'>👤 User (Resume Task):</b><br><span style='font-size: 1.05em;'>Resuming: {task_name}</span></div>"
            self.chat_history.append(user_bubble)
            
            self.run_btn.setDisabled(True)
            self.resume_btn.setDisabled(True)
            self.stop_btn.setDisabled(False)
            self.ledger_view.clear()

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

    def prompt_user_input(self, question):
        text, ok = QInputDialog.getMultiLineText(self, "Aquila Requires Input", question)
        if ok and text:
            self.worker.user_reply = text
        else:
            self.worker.user_reply = "User declined to answer or cancelled."
        self.worker.reply_event.set()

    def execute_task(self):
        user_prompt = self.chat_input.text().strip()
        if not user_prompt: return

        mode_selection = self.mode_selector.currentText()
        if mode_selection == "Chat Mode": mode_flag = "chat"
        elif mode_selection == "Research Mode": mode_flag = "research"
        elif mode_selection == "Writing Mode": mode_flag = "writing"
        else: mode_flag = "autonomous"
        
        # New Unique Task Name Generator
        clean_prefix = re.sub(r'[^a-zA-Z0-9]', '', "_".join(user_prompt.split()[:3]).lower())
        task_name = f"{clean_prefix}_{int(time.time())}"

        user_bubble = f"<div style='margin-top: 15px; margin-bottom: 10px; padding: 10px; border-left: 4px solid #e74c3c; background-color: rgba(231, 76, 60, 0.1);'><b style='color: #e74c3c;'>👤 User ({mode_selection}):</b><br><span style='font-size: 1.05em;'>{user_prompt}</span></div>"
        self.chat_history.append(user_bubble)
        self.chat_input.clear()
        
        self.run_btn.setDisabled(True)
        self.resume_btn.setDisabled(True)
        self.stop_btn.setDisabled(False)
        self.ledger_view.clear()

        # Pass attachments into the worker
        self.worker = AgentWorker(
            task_name, 
            user_prompt, 
            mode_flag,
            self.attached_chunks,
            self.attached_images
        )
        
        # Reset GUI attachment state so files don't accidentally carry over to the next prompt
        self.attached_chunks = []
        self.attached_images = []
        self.attach_button.setText("📎 Attach Files")

        self.worker.ledger_signal.connect(self.update_ledger_ui)
        self.worker.ask_user_signal.connect(self.prompt_user_input)
        self.worker.finished_signal.connect(self.task_finished)
        self.worker.start()

    def update_ledger_ui(self, text):
        self.ledger_view.clear()
        self.ledger_view.append(text)
        
        if not self.worker: return
        
        state_file = None
        if self.worker.mode == "writing":
            state_file = Path("Agent-Drafts/active_draft_state.json")
        else:
            # Both Task and Research modes use the standard state tracker!
            state_file = Path(f"Agent-Tasks/{self.worker.task_name}.json")
            
        if state_file and state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                    
                    if self.worker.mode == "writing":
                        title = state_data.get('title', 'Draft')
                        synopsis = state_data.get('synopsis', '')
                        
                        html_state = f"<h2 style='color: #9b59b6; border-bottom: 1px solid #555; padding-bottom: 5px;'>📝 Active Document: {title}</h2>"
                        if synopsis:
                            html_state += f"<p style='font-style: italic; color: #7f8c8d;'>{synopsis}</p>"
                            
                        html_state += "<ul style='list-style-type: none; padding-left: 0;'>"
                        for i, sec in enumerate(state_data.get("sections", [])):
                            word_count = len(sec.get('content', '').split())
                            html_state += f"<li style='margin-bottom: 12px; padding: 10px; background-color: rgba(155, 89, 182, 0.05); border-left: 4px solid #9b59b6; border-radius: 4px;'>"
                            html_state += f"<b style='color: #9b59b6;'>Section {i+1}:</b> {sec.get('header', '')}"
                            html_state += f"<br><i style='color: #bdc3c7; font-size: 0.9em; display: block;'>Content: {word_count} words written</i>"
                            html_state += "</li>"
                        html_state += "</ul>"
                        
                        self.state_view.setHtml(html_state)
                        
                        canvas_text = f"# {title}\n\n"
                        for sec in state_data.get("sections", []):
                            canvas_text += f"## {sec.get('header', '')}\n{sec.get('content', '')}\n\n"
                            
                        canvas_html = markdown.markdown(canvas_text, extensions=['fenced_code', 'tables'])
                        self.canvas_editor.setHtml(f"<div style='font-family: Arial, sans-serif; line-height: 1.6;'>{canvas_html}</div>")
                        
                    else:
                        # Keep your existing checklist HTML renderer for Tasks and Research here!
                        pass

            except Exception as e:
                pass

    def task_finished(self, result):
        html_content = markdown.markdown(result, extensions=['fenced_code', 'tables'])
        
        agent_bubble = f"<div style='margin-bottom: 20px; padding: 10px; border-left: 4px solid #3498db; background-color: rgba(52, 152, 219, 0.05);'>"
        agent_bubble += f"<b style='color: #3498db;'>🦅 Aquila:</b><br><div style='line-height: 1.5;'>{html_content}</div></div>"
        
        self.chat_history.append(agent_bubble)
        
        self.run_btn.setDisabled(False)
        self.resume_btn.setDisabled(False)
        self.stop_btn.setDisabled(True)
        self.chat_input.setFocus()

if __name__ == "__main__":
    import re
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = AquilaOS()
    window.show()
    sys.exit(app.exec())