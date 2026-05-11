import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

# Import Aquila's Brain
from main import global_agent

# ---------------------------------------------------------
# 1. THE BACKGROUND WORKER THREAD
# ---------------------------------------------------------
class AgentWorker(QThread):
    # Native Qt Signals
    ledger_signal = Signal(str)
    finished_signal = Signal(str)

    def __init__(self, task_name, prompt, mode):
        super().__init__()
        self.task_name = task_name
        self.prompt = prompt
        self.mode = mode

    def run(self):
        try:
            # We pass the Qt Signal directly into the pure Python callback!
            result = global_agent.run_unified_task(
                task_name=self.task_name,
                user_request=self.prompt,
                mode=self.mode,
                ui_callback=self.ledger_signal.emit 
            )
            self.finished_signal.emit(f"✅ Task Completed:\n{result}")
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

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # The Splitter allows dragging and resizing the panels
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- LEFT PANEL: Chat / Controls ---
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Autonomous Task", "Research Mode"])
        left_layout.addWidget(QLabel("Operation Mode:"))
        left_layout.addWidget(self.mode_selector)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.append("<b>Aquila:</b> System Online. I am running on native Qt.")
        left_layout.addWidget(self.chat_history)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Assign a task (e.g., 'Draft an essay...')")
        self.chat_input.returnPressed.connect(self.execute_task)
        left_layout.addWidget(self.chat_input)

        # --- MIDDLE PANEL: The Canvas (Writing/Code) ---
        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.addWidget(QLabel("📝 The Canvas"))
        
        self.canvas_editor = QTextEdit()
        self.canvas_editor.setFont(QFont("Courier New", 11))
        middle_layout.addWidget(self.canvas_editor)

        # --- RIGHT PANEL: The Ledger ---
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.addWidget(QLabel("🧠 OS Ledger"))
        
        self.ledger_view = QTextEdit()
        self.ledger_view.setReadOnly(True)
        self.ledger_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        right_layout.addWidget(self.ledger_view)

        # Add panels to splitter
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.middle_panel)
        self.splitter.addWidget(self.right_panel)
        
        # Set panel ratios (20% Chat, 50% Canvas, 30% Ledger)
        self.splitter.setSizes([280, 700, 420])
        self.worker = None

    def execute_task(self):
        user_prompt = self.chat_input.text().strip()
        if not user_prompt:
            return

        mode_selection = self.mode_selector.currentText()
        mode_flag = "research" if mode_selection == "Research Mode" else "autonomous"
        task_name = "_".join(user_prompt.split()[:3]).lower()

        self.chat_history.append(f"<br><b>User ({mode_selection}):</b> {user_prompt}")
        self.chat_input.clear()
        self.chat_input.setDisabled(True)
        
        self.ledger_view.clear()
        self.ledger_view.append(f"Initializing {mode_selection} Engine...")

        # Start Aquila in a background thread
        self.worker = AgentWorker(task_name, user_prompt, mode_flag)
        self.worker.ledger_signal.connect(self.update_ledger_ui)
        self.worker.finished_signal.connect(self.task_finished)
        self.worker.start()

    def update_ledger_ui(self, text):
        self.ledger_view.clear()
        self.ledger_view.append(text)
        
        import os, json
        draft_path = "Agent-Drafts/active_draft_state.json"
        if os.path.exists(draft_path):
            try:
                with open(draft_path, "r", encoding="utf-8") as f:
                    draft_state = json.load(f)
                    
                canvas_text = f"# {draft_state.get('title', 'Draft')}\n\n"
                for sec in draft_state.get("sections", []):
                    canvas_text += f"## {sec['header']}\n{sec['content']}\n\n"
                    
                self.canvas_editor.setPlainText(canvas_text)
            except:
                pass

    def task_finished(self, result):
        self.chat_history.append(f"<br><b>Aquila:</b> {result}")
        self.chat_input.setDisabled(False)
        self.chat_input.setFocus()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = AquilaOS()
    window.show()
    sys.exit(app.exec())