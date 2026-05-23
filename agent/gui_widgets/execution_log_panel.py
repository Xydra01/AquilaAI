"""Execution log + optional task state tracker tabs."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QTabWidget, QTextEdit, QWidget
from PySide6.QtGui import QFont

from gui_formatting import format_ledger_html
from gui_richtext import SmartScrollTextEdit, apply_panel_style


class ExecutionLogPanel(QWidget):
    def __init__(self, main_window, *, show_state_tracker: bool = True):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tab_widget = QTabWidget()
        self.ledger_view = SmartScrollTextEdit()
        apply_panel_style(self.ledger_view, "ledger", dark=main_window.dark_mode)
        self.tab_widget.addTab(self.ledger_view, "Execution Log")
        self.state_view = None
        if show_state_tracker:
            self.state_view = QTextEdit()
            self.state_view.setReadOnly(True)
            self.state_view.setFont(QFont("Consolas", 10))
            self.tab_widget.addTab(self.state_view, "Task State Tracker")
        layout.addWidget(self.tab_widget)

    def refresh_theme(self, *, dark: bool) -> None:
        apply_panel_style(self.ledger_view, "ledger", dark=dark)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        html = format_ledger_html(text)
        if clear:
            self.ledger_view.set_html_smart(html)
        else:
            self.ledger_view.append_smart(html)

    def reset_scroll_follow(self) -> None:
        self.ledger_view.reset_scroll_follow()

    def set_state_html(self, html: str) -> None:
        if self.state_view is not None:
            self.state_view.setHtml(html)
