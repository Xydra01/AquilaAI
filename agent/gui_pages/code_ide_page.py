"""Code Mode IDE workspace: file tree, editors, agent rail, problems/tests."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTextEdit,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
    QWidget,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from gui_formatting import format_ledger_html
from gui_pages.base import BaseModePage
from gui_richtext import SmartScrollTextEdit, apply_panel_style
from gui_state import render_code_canvas_html
from tools import is_ignored_code_path


class CodeIdePage(BaseModePage):
    MODE = "code"
    MODE_LABEL = "Code Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        self.open_inplace_btn = QPushButton("Open in-place")
        self.open_inplace_btn.clicked.connect(self._open_in_place)
        self.import_sandbox_btn = QPushButton("Import sandbox")
        self.import_sandbox_btn.clicked.connect(self._import_sandbox)
        self.new_project_btn = QPushButton("New project")
        self.new_project_btn.clicked.connect(self._new_project)
        self.sync_btn = QPushButton("Sync to disk")
        self.sync_btn.clicked.connect(self._sync_disk)
        self.status_label = QLabel("No project open")
        self.status_label.setStyleSheet("color: #7f8c8d;")
        for w in (
            self.open_inplace_btn,
            self.import_sandbox_btn,
            self.new_project_btn,
            self.sync_btn,
        ):
            toolbar.addWidget(w)
        toolbar.addStretch()
        toolbar.addWidget(self.status_label)
        root_layout.addLayout(toolbar)

        main_split = QSplitter(Qt.Horizontal)
        root_layout.addWidget(main_split, stretch=3)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabel("Files")
        self.file_tree.setMinimumWidth(180)
        main_split.addWidget(self.file_tree)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_tabs = QTabWidget()
        center_layout.addWidget(self.editor_tabs)
        main_split.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_history = SmartScrollTextEdit()
        apply_panel_style(self.chat_history, "chat", dark=main_window.dark_mode)
        right_layout.addWidget(self.chat_history, stretch=2)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Code task (TDD, implement, fix)...")
        self.chat_input.returnPressed.connect(main_window.execute_task)
        right_layout.addWidget(self.chat_input)
        btn_row = QHBoxLayout()
        self.attach_button = QPushButton("📎")
        self.attach_button.clicked.connect(main_window.open_attachment_dialog)
        self.run_btn = QPushButton("▶️ Run")
        self.run_btn.clicked.connect(main_window.execute_task)
        self.resume_btn = QPushButton("📂")
        self.resume_btn.clicked.connect(main_window.resume_task_dialog)
        self.stop_btn = QPushButton("🛑")
        self.stop_btn.clicked.connect(main_window.stop_task)
        self.stop_btn.setDisabled(True)
        for w in (self.attach_button, self.run_btn, self.resume_btn, self.stop_btn):
            btn_row.addWidget(w)
        right_layout.addLayout(btn_row)
        self.ledger_view = SmartScrollTextEdit()
        apply_panel_style(self.ledger_view, "ledger", dark=main_window.dark_mode)
        right_layout.addWidget(QLabel("Execution log"))
        right_layout.addWidget(self.ledger_view, stretch=2)
        main_split.addWidget(right)
        main_split.setSizes([200, 550, 350])

        pending_row = QHBoxLayout()
        self.pending_view = QPlainTextEdit()
        self.pending_view.setReadOnly(True)
        self.pending_view.setMaximumHeight(100)
        self.pending_view.setPlaceholderText("Pending diffs (review queue)")
        pending_row.addWidget(self.pending_view, stretch=1)
        self.accept_patch_btn = QPushButton("Accept")
        self.accept_patch_btn.clicked.connect(self._accept_patch)
        self.accept_all_btn = QPushButton("Accept all")
        self.accept_all_btn.clicked.connect(self._accept_all_patches)
        self.reject_patch_btn = QPushButton("Reject")
        self.reject_patch_btn.clicked.connect(self._reject_patch)
        for w in (self.accept_patch_btn, self.accept_all_btn, self.reject_patch_btn):
            pending_row.addWidget(w)
        root_layout.addLayout(pending_row)

        bottom_split = QSplitter(Qt.Horizontal)
        self.problems_view = QTextEdit()
        self.problems_view.setReadOnly(True)
        self.problems_view.setMaximumHeight(120)
        self.problems_view.setPlaceholderText("Lint / problems")
        self.test_view = QTextEdit()
        self.test_view.setReadOnly(True)
        self.test_view.setMaximumHeight(120)
        self.test_view.setPlaceholderText("Pytest status")
        self.state_view = QTextEdit()
        self.state_view.setReadOnly(True)
        self.state_view.setMaximumHeight(120)
        bottom_split.addWidget(self.problems_view)
        bottom_split.addWidget(self.test_view)
        bottom_split.addWidget(self.state_view)
        root_layout.addWidget(bottom_split, stretch=0)

        self._last_pytest_summary = ""

    def _open_in_place(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open codebase in-place")
        if not path:
            return
        from tool_library import code_canvas_tools

        name = Path(path).name or "project"
        result = code_canvas_tools.attach_existing_repo(path, name)
        QMessageBox.information(self, "Open project", result)
        self.refresh_state()

    def _import_sandbox(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Import codebase to sandbox")
        if not path:
            return
        from tool_library import code_canvas_tools

        name = Path(path).name or "imported"
        result = code_canvas_tools.import_codebase(path, name, workspace_mode="sandbox")
        QMessageBox.information(self, "Import sandbox", result[:2000])
        self.refresh_state()

    def _new_project(self) -> None:
        from tool_library import code_canvas_tools

        result = code_canvas_tools.init_code_project("new_project", "", "python")
        QMessageBox.information(self, "New project", result)
        self.refresh_state()

    def _sync_disk(self) -> None:
        from tool_library import code_canvas_tools

        result = code_canvas_tools.sync_project_to_disk()
        QMessageBox.information(self, "Sync", result[:2000])
        self.refresh_state()

    def _accept_patch(self) -> None:
        from tool_library import code_canvas_tools

        QMessageBox.information(self, "Pending patch", code_canvas_tools.accept_pending_patch(0))
        self.refresh_state()

    def _reject_patch(self) -> None:
        from tool_library import code_canvas_tools

        QMessageBox.information(self, "Pending patch", code_canvas_tools.reject_pending_patch(0))
        self.refresh_state()

    def _accept_all_patches(self) -> None:
        from tool_library import code_canvas_tools

        QMessageBox.information(self, "Pending patches", code_canvas_tools.accept_all_pending_patches())
        self.refresh_state()

    def append_chat_html(self, html: str) -> None:
        self.chat_history.append_smart(html)

    def clear_chat_display(self) -> None:
        self.chat_history.clear()
        self.chat_history.reset_scroll_follow()
        self.ledger_view.reset_scroll_follow()

    def get_chat_input_text(self) -> str:
        return self.chat_input.text().strip()

    def clear_chat_input(self) -> None:
        self.chat_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.resume_btn.setDisabled(running)
        self.stop_btn.setDisabled(not running)

    def refresh_theme(self, *, dark: bool) -> None:
        apply_panel_style(self.chat_history, "chat", dark=dark)
        apply_panel_style(self.ledger_view, "ledger", dark=dark)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        html = format_ledger_html(text)
        if clear:
            self.ledger_view.set_html_smart(html)
        else:
            self.ledger_view.append_smart(html)
        if "run_pytest" in text.lower() or "pytest" in text.lower():
            self._last_pytest_summary = text[-800:]

    def refresh_state(self) -> None:
        from workspace_paths import agent_data_path

        buf_path = agent_data_path("Agent-Code", "active_code_state.json")
        if not buf_path.exists():
            self.status_label.setText("No project open")
            return
        try:
            with open(buf_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
        except Exception:
            return

        from tool_library import code_canvas_tools

        pruned = code_canvas_tools._prune_ignored_files(state_data)
        if pruned:
            code_canvas_tools._save_state(state_data)

        root = state_data.get("root", "?")
        mode = state_data.get("workspace_mode", "sandbox")
        dep = state_data.get("dependency_hints", {})
        dep_note = f" | {dep['venv_dir']}/ skipped" if dep.get("venv_dir") else ""
        self.status_label.setText(
            f"{state_data.get('project_name', '?')} | {mode} | {root}{dep_note}"
        )

        task_ledger = None
        if self._worker:
            task_path = agent_data_path("Agent-Tasks", f"{self._worker.task_name}.json")
            if task_path.exists():
                try:
                    raw = task_path.read_text(encoding="utf-8").strip()
                    if raw:
                        task_ledger = json.loads(raw)
                except json.JSONDecodeError:
                    task_ledger = {
                        "status": "in_progress",
                        "steps": [
                            {
                                "status": "in_progress",
                                "description": "Task ledger file is temporarily unreadable (retry refresh)",
                            }
                        ],
                    }

        self.state_view.setHtml(render_code_canvas_html(state_data, task_ledger))
        patches = code_canvas_tools.list_pending_patches()
        if patches:
            lines = []
            for i, patch in enumerate(patches):
                lines.append(f"[{i}] {patch.get('path', '?')}")
                diff = patch.get("unified_diff", "")
                if diff:
                    lines.append(diff[:600])
            self.pending_view.setPlainText("\n\n".join(lines))
        else:
            self.pending_view.clear()
        self._populate_file_tree(state_data)
        self._populate_editors(state_data)
        self._populate_problems(state_data)
        if self._last_pytest_summary:
            self.test_view.setPlainText(self._last_pytest_summary[-1200:])

    def _populate_file_tree(self, state_data: dict) -> None:
        self.file_tree.clear()
        root_item = QTreeWidgetItem([state_data.get("project_name", "Project")])
        self.file_tree.addTopLevelItem(root_item)
        files_by_dir: dict[str, list] = {}
        for f in state_data.get("files", []):
            path = f.get("path", "")
            if is_ignored_code_path(path):
                continue
            parts = Path(path).parts
            if not parts:
                continue
            dir_key = str(Path(*parts[:-1])) if len(parts) > 1 else "."
            files_by_dir.setdefault(dir_key, []).append((parts[-1], f))

        for dir_name in sorted(files_by_dir.keys()):
            dir_item = QTreeWidgetItem([dir_name if dir_name != "." else "(root)"])
            root_item.addChild(dir_item)
            for fname, meta in sorted(files_by_dir[dir_name]):
                lint = meta.get("lint_status", "?")
                dirty = "*" if meta.get("dirty") else ""
                child = QTreeWidgetItem([f"{fname}{dirty} [{lint}]"])
                child.setData(0, Qt.UserRole, meta.get("path"))
                dir_item.addChild(child)
        root_item.setExpanded(True)

    def _populate_editors(self, state_data: dict) -> None:
        while self.editor_tabs.count() > 0:
            self.editor_tabs.removeTab(0)
        mono = QFont("Courier New", 10)
        for f in state_data.get("files", []):
            path = f.get("path", "file")
            if is_ignored_code_path(path):
                continue
            editor = QPlainTextEdit()
            editor.setFont(mono)
            editor.setReadOnly(True)
            content = f.get("content", "")
            if not content and f.get("indexed_only"):
                disk = Path(state_data.get("root", ".")) / path
                if disk.exists():
                    try:
                        content = disk.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        content = "(unable to read from disk)"
            editor.setPlainText(content or "")
            label = Path(path).name
            if f.get("dirty"):
                label += " *"
            self.editor_tabs.addTab(editor, label)

    def _populate_problems(self, state_data: dict) -> None:
        lines = []
        for f in state_data.get("files", []):
            st = f.get("lint_status", "unknown")
            if st not in ("ok", "unknown"):
                lines.append(f"{f.get('path')}: {st}")
        self.problems_view.setPlainText("\n".join(lines) if lines else "No lint issues recorded.")
