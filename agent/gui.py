import sys
import threading
import json
import os
import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox,
    QTabWidget, QInputDialog
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor

# Import Aquila's Brain and Tools
from main import global_agent
from tool_library import agent_tools

# ---------------------------------------------------------
# 1. THE BACKGROUND WORKER THREAD
# ---------------------------------------------------------
class AgentWorker(QThread):
    ledger_signal = Signal(str)
    finished_signal = Signal(str)
    ask_user_signal = Signal(str) # Triggers the GUI popup

    def __init__(self, task_name, prompt, mode):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode
        
        # Cross-thread communication flags
        self.cancel_flag = False
        self.user_reply = ""
        self.reply_event = threading.Event()

    def _ask_user_bridge(self, question: str) -> str:
        """This function pauses the thread, asks the GUI for input, and waits."""
        self.reply_event.clear()
        self.ask_user_signal.emit(question)
        self.reply_event.wait() # Thread sleeps here until user clicks OK
        return self.user_reply

    def run(self):
        # Bind the global callback to this thread's bridge
        agent_tools.USER_INPUT_CALLBACK = self._ask_user_bridge
        
        try:
            if self.mode == "chat":
                # Fast Chat Bypass - No tool loops
                self.ledger_signal.emit("Bypassing execution engine. Processing conversational chat...")
                
                # --- NEW: Real-Time Context Injection ---
                current_time = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
                facts = global_agent.memory.get_all_facts()
                
                system_prompt = (
                    f"You are Aquila, an advanced AI assistant. "
                    f"Current Date and Time: {current_time}. "
                    f"Context & Facts: {facts}"
                )
                
                history = [{"role": "system", "content": system_prompt}]
                history.append({"role": "user", "content": self.prompt})
                
                # Send to Ollama
                response = global_agent.client.chat(history)
                self.finished_signal.emit(f"✅ {response}")
        except Exception as e:
            self.finished_signal.emit(f"❌ Engine Error: {str(e)}")

# ---------------------------------------------------------
# 2. THE MAIN WINDOW (AQUILA OS 3.2)
# ---------------------------------------------------------
class AquilaOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🦅 Aquila OS 3.2 - Desktop Canvas")
        self.resize(1400, 800)
        self.dark_mode = False

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Control Bar
        top_bar = QHBoxLayout()
        self.theme_btn = QPushButton("🌙 Toggle Dark Mode")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- LEFT PANEL: Chat / Controls ---
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Chat Mode", "Autonomous Task", "Writing Mode", "Research Mode"])
        left_layout.addWidget(QLabel("Operation Mode:"))
        left_layout.addWidget(self.mode_selector)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.append("<b>Aquila:</b> System Online. I am running on native Qt.")
        left_layout.addWidget(self.chat_history)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Assign a task or say hello...")
        self.chat_input.returnPressed.connect(self.execute_task)
        left_layout.addWidget(self.chat_input)

        # Execution Buttons
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("▶️ Run")
        self.run_btn.clicked.connect(self.execute_task)
        self.stop_btn = QPushButton("🛑 Emergency Stop")
        self.stop_btn.clicked.connect(self.stop_task)
        self.stop_btn.setDisabled(True)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.stop_btn)
        left_layout.addLayout(btn_layout)

        # --- MIDDLE PANEL: The Canvas ---
        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.addWidget(QLabel("📝 The Canvas"))
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setFont(QFont("Courier New", 11))
        middle_layout.addWidget(self.canvas_editor)

        # --- RIGHT PANEL: The Ledger & State Tracker ---
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        
        self.tab_widget = QTabWidget()
        
        # Tab 1: Execution Log
        self.ledger_view = QTextEdit()
        self.ledger_view.setReadOnly(True)
        self.ledger_view.setFont(QFont("Consolas", 10))
        self.tab_widget.addTab(self.ledger_view, "Execution Log")
        
        # Tab 2: State / Scratchpad Tracker
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

        # Start in Dark Mode
        self.toggle_theme()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            # Native Qt Dark Palette
            self.setStyleSheet("""
                QWidget { background-color: #1e1e1e; color: #d4d4d4; }
                QTextEdit, QLineEdit { background-color: #252526; border: 1px solid #3e3e42; }
                QPushButton { background-color: #333333; border: 1px solid #3e3e42; padding: 5px; }
                QPushButton:hover { background-color: #3e3e42; }
                QTabWidget::pane { border: 1px solid #3e3e42; }
                QTabBar::tab { background: #252526; padding: 5px 10px; }
                QTabBar::tab:selected { background: #3e3e42; }
            """)
            self.ledger_view.setStyleSheet("color: #4CAF50;") # Hacker Green for logs
        else:
            self.setStyleSheet("") # Revert to system default
            self.ledger_view.setStyleSheet("color: #006400;") # Dark green for light mode

    def stop_task(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_flag = True
            self.ledger_view.append("\n\n🛑 ABORT SIGNAL SENT. Waiting for agent to safely halt...\n")
            self.stop_btn.setDisabled(True)

    def prompt_user_input(self, question):
        # This pops up when ask_user is triggered by the background thread
        text, ok = QInputDialog.getMultiLineText(self, "Aquila Requires Input", question)
        if ok and text:
            self.worker.user_reply = text
        else:
            self.worker.user_reply = "User declined to answer or cancelled."
        
        # Resume the thread
        self.worker.reply_event.set()

    def execute_task(self):
        user_prompt = self.chat_input.text().strip()
        if not user_prompt:
            return

        mode_selection = self.mode_selector.currentText()
        if mode_selection == "Chat Mode": mode_flag = "chat"
        elif mode_selection == "Research Mode": mode_flag = "research"
        elif mode_selection == "Writing Mode": mode_flag = "writing"
        else: mode_flag = "autonomous"
        
        task_name = "_".join(user_prompt.split()[:3]).lower()

        self.chat_history.append(f"<br><b>User ({mode_selection}):</b> {user_prompt}")
        self.chat_input.clear()
        
        self.run_btn.setDisabled(True)
        self.stop_btn.setDisabled(False)
        self.ledger_view.clear()

        # Start Aquila in a background thread
        self.worker = AgentWorker(task_name, user_prompt, mode_flag)
        self.worker.ledger_signal.connect(self.update_ledger_ui)
        self.worker.ask_user_signal.connect(self.prompt_user_input)
        self.worker.finished_signal.connect(self.task_finished)
        self.worker.start()

    def update_ledger_ui(self, text):
        self.ledger_view.clear()
        self.ledger_view.append(text)
        
        if not self.worker: return
        
        import os, json
        from pathlib import Path
        
        # --- Update the State/Scratchpad Tracker ---
        state_file = None
        if self.worker.mode == "writing":
            state_file = Path("Agent-Drafts/active_draft_state.json")
        elif self.worker.mode in ["autonomous", "task"]:
            # In Task mode, Aquila saves her scratchpad under her task name
            state_file = Path(f"Agent-Tasks/{self.worker.task_name}.json")
        elif self.worker.mode == "research":
            state_file = Path(f"Agent-Research/{self.worker.task_name}.json")
            
        if state_file and state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    # Formatted JSON dump for the State Tracker tab
                    state_data = json.load(f)
                    self.state_view.setPlainText(json.dumps(state_data, indent=4))
                    
                    # If she is writing, also update the middle Canvas
                    if self.worker.mode == "writing":
                        canvas_text = f"# {state_data.get('title', 'Draft')}\n\n"
                        for sec in state_data.get("sections", []):
                            canvas_text += f"## {sec['header']}\n{sec['content']}\n\n"
                        self.canvas_editor.setPlainText(canvas_text)
            except Exception:
                pass

    def task_finished(self, result):
        self.chat_history.append(f"<br><b>Aquila:</b> {result}")
        self.run_btn.setDisabled(False)
        self.stop_btn.setDisabled(True)
        self.chat_input.setFocus()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = AquilaOS()
    window.show()
    sys.exit(app.exec())