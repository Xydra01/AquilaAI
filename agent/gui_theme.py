"""Shared workspace theme tokens and stylesheets for Aquila GUI."""
from __future__ import annotations

MODE_ACCENTS: dict[str, str] = {
    "chat": "#4a9eff",
    "autonomous": "#9b59b6",
    "research": "#e67e22",
    "writing": "#27ae60",
    "code": "#3498db",
    "learn": "#95a5a6",
    "character": "#e84393",
}

SPLITTER_DEFAULTS: dict[str, list[int]] = {
    "chat": [],
    "autonomous": [300, 600, 500],
    "task": [280, 520, 480],
    "research": [320, 520, 420],
    "writing": [280, 700, 380],
    "code": [200, 550, 350],
}

DARK_STYLESHEET = """
QWidget { background-color: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI', sans-serif; }
QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget {
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
"""

LIGHT_STYLESHEET = """
QWidget { font-family: 'Segoe UI', sans-serif; color: #1a1a1a; }
QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget {
    background-color: #ffffff; border: 1px solid #d0d7de; border-radius: 4px; padding: 4px;
}
QLineEdit { padding: 6px 8px; }
QPushButton {
    background-color: #f6f8fa; border: 1px solid #d0d7de; padding: 6px 12px; border-radius: 4px;
}
QPushButton:hover { background-color: #eaeef2; }
QTabBar::tab { padding: 6px 12px; }
QSplitter::handle { background: #d0d7de; width: 3px; }
"""


def main_window_stylesheet(*, dark: bool) -> str:
    return DARK_STYLESHEET if dark else LIGHT_STYLESHEET


def mode_accent_style(mode: str) -> str:
    color = MODE_ACCENTS.get(mode, "#7f8c8d")
    return f"border-left: 4px solid {color}; padding-left: 8px;"
