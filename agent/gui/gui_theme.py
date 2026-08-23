"""Shared workspace theme tokens and stylesheets for Aquila GUI."""
from __future__ import annotations

MODE_ACCENTS: dict[str, str] = {
    # Kept per-mode so existing mode headers remain distinct.
    "chat": "#0066FF",
    "autonomous": "#9b59b6",
    "research": "#e67e22",
    "writing": "#27ae60",
    "code": "#3498db",
    "learn": "#95a5a6",
    "character": "#e84393",
    "data": "#f1c40f",
}

SPLITTER_DEFAULTS: dict[str, list[int]] = {
    "chat": [],
    "autonomous": [300, 600, 500],
    "task": [280, 520, 480],
    "research": [320, 520, 420],
    "writing": [280, 700, 380],
    "code": [200, 550, 350],
    "data": [280, 520, 480],
}

DARK_STYLESHEET = """
QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget {
    background-color: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #3E3E42;
    border-radius: 8px;
    padding: 10px;
    selection-background-color: #0078D4;
}
QLineEdit { padding: 8px 12px; min-height: 1.2em; }
QPushButton {
    background-color: #333333;
    color: #E0E0E0;
    border: 1px solid #3E3E42;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 600;
}
QPushButton:hover { background-color: #3E3E42; border-color: #555555; }
QPushButton:pressed { background-color: #2D2D2D; }
QPushButton:disabled { color: #6e6e6e; background-color: #2a2a2a; border-color: #2a2a2a; }
QTabWidget::pane { border: 1px solid #3E3E42; border-radius: 8px; }
QTabBar::tab { background: #252526; color: #A0A0A0; padding: 10px 20px; margin-right: 2px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #333333; font-weight: bold; color: #FFFFFF; border-bottom: 2px solid #0078D4; }
QLabel { color: #E0E0E0; }
#instanceLabel { color: #E0E0E0; }
QCheckBox, QRadioButton { color: #E0E0E0; }
QComboBox, QSpinBox { background: #333333; color: #E0E0E0; border: 1px solid #3E3E42; padding: 6px 12px; border-radius: 8px; }
QComboBox QAbstractItemView { background-color: #2D2D2D; color: #E0E0E0; selection-background-color: #0078D4; }
QGroupBox { color: #E0E0E0; font-weight: bold; background-color: #252526; border: 1px solid #3E3E42; border-radius: 8px; margin-top: 10px; padding-top: 10px; }
QToolBox, QToolBox QWidget { background-color: #2D2D2D; color: #E0E0E0; }
QToolBox::tab { background-color: #333333; color: #E0E0E0; border-radius: 4px; padding: 4px; }
QToolBox::tab:selected { font-weight: bold; background-color: #3E3E42; }
QSplitter::handle { background: #3E3E42; width: 3px; border-radius: 1px; }
QScrollArea { background-color: transparent; border: none; }
QScrollArea > QWidget > QWidget { background-color: #252526; }
"""

SETTINGS_PANEL_DARK = """
QWidget[aquilaPanel="true"] { background-color: #252526; color: #E0E0E0; }
QLabel[aquilaHint="true"] { color: #8e8e8e; font-size: 11px; }
QScrollArea { background-color: transparent; border: none; }
QScrollArea > QWidget > QWidget { background-color: #252526; }
"""

SETTINGS_PANEL_LIGHT = """
QWidget[aquilaPanel="true"] { background-color: #FFFFFF; color: #2D3748; }
QLabel[aquilaHint="true"] { color: #7f8c8d; font-size: 11px; }
QScrollArea { background-color: transparent; border: none; }
QScrollArea > QWidget > QWidget { background-color: #FFFFFF; }
"""

LIGHT_STYLESHEET = """
QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 8px;
    padding: 10px;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}
QLineEdit { padding: 8px 12px; }
QPushButton {
    background-color: #F8F9FA;
    border: 1px solid #E5E5E5;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 600;
}
QPushButton:hover { background-color: #E2E8F0; border-color: #CBD5E0; }
QPushButton:pressed { background-color: #EDF2F7; }
QPushButton:disabled { color: #A0AEC0; background-color: #F7FAFC; border-color: #E2E8F0; }
QTabWidget::pane { border: 1px solid #E5E5E5; border-radius: 8px; }
QTabBar::tab { background: #F8F9FA; padding: 10px 20px; margin-right: 2px; border-top-left-radius: 8px; border-top-right-radius: 8px; border: 1px solid transparent; border-bottom: none; }
QTabBar::tab:selected { background: #FFFFFF; border: 1px solid #E5E5E5; font-weight: bold; color: #1A1A1A; border-bottom: 2px solid #0078D4; }
QLabel { color: #2D3748; }
#instanceLabel { color: #2D3748; }
QComboBox, QSpinBox { background: #F8F9FA; border: 1px solid #E5E5E5; padding: 6px 12px; border-radius: 8px; color: #1A1A1A; }
QToolBox, QToolBox QWidget { background-color: #FFFFFF; color: #1A1A1A; }
QToolBox::tab { background-color: #F8F9FA; color: #1A1A1A; border-radius: 4px; padding: 4px; }
QToolBox::tab:selected { font-weight: bold; background-color: #E2E8F0; }
QSplitter::handle { background: #E5E5E5; width: 3px; border-radius: 1px; }
QScrollArea { background-color: transparent; border: none; }
QScrollArea > QWidget > QWidget { background-color: #FFFFFF; }
"""


def main_window_stylesheet(*, dark: bool) -> str:
    return DARK_STYLESHEET if dark else LIGHT_STYLESHEET


def settings_panel_stylesheet(*, dark: bool) -> str:
    return SETTINGS_PANEL_DARK if dark else SETTINGS_PANEL_LIGHT


def muted_text_color(*, dark: bool) -> str:
    return "#8e8e8e" if dark else "#7f8c8d"


MESSAGE_BOX_DARK = """
QMessageBox {
    background-color: #2D2D2D;
    color: #E0E0E0;
}
QMessageBox QLabel {
    color: #E0E0E0;
    background-color: transparent;
    min-width: 280px;
}
QMessageBox QPushButton {
    background-color: #333333;
    color: #E0E0E0;
    border: 1px solid #3E3E42;
    padding: 6px 16px;
    border-radius: 6px;
    min-width: 72px;
}
QMessageBox QPushButton:hover {
    background-color: #3E3E42;
    border-color: #555555;
}
QMessageBox QPushButton:pressed {
    background-color: #252526;
}
"""

MESSAGE_BOX_LIGHT = """
QMessageBox {
    background-color: #FFFFFF;
    color: #2D3748;
}
QMessageBox QLabel {
    color: #2D3748;
    background-color: transparent;
    min-width: 280px;
}
QMessageBox QPushButton {
    background-color: #F8F9FA;
    color: #2D3748;
    border: 1px solid #E5E5E5;
    padding: 6px 16px;
    border-radius: 6px;
    min-width: 72px;
}
QMessageBox QPushButton:hover {
    background-color: #E2E8F0;
    border-color: #CBD5E0;
}
"""


def message_box_stylesheet(*, dark: bool) -> str:
    return MESSAGE_BOX_DARK if dark else MESSAGE_BOX_LIGHT


DIALOG_DARK = """
QDialog {
    background-color: #2D2D2D;
    color: #E0E0E0;
}
QDialog QLabel {
    color: #E0E0E0;
    background-color: transparent;
}
QDialog QTextEdit, QDialog QPlainTextEdit {
    background-color: #252526;
    color: #E0E0E0;
    border: 1px solid #3E3E42;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #0078D4;
}
QDialog QTabWidget::pane {
    border: 1px solid #3E3E42;
    background-color: #252526;
    border-radius: 6px;
}
QDialog QTabBar::tab {
    background-color: #333333;
    color: #A0A0A0;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QDialog QTabBar::tab:selected {
    background-color: #3E3E42;
    color: #FFFFFF;
}
QDialog QPushButton {
    background-color: #333333;
    color: #E0E0E0;
    border: 1px solid #3E3E42;
    padding: 6px 16px;
    border-radius: 6px;
    min-width: 88px;
}
QDialog QPushButton:hover {
    background-color: #3E3E42;
    border-color: #555555;
}
QDialog QPushButton:pressed {
    background-color: #252526;
}
"""

DIALOG_LIGHT = """
QDialog {
    background-color: #FFFFFF;
    color: #2D3748;
}
QDialog QLabel {
    color: #2D3748;
    background-color: transparent;
}
QDialog QTextEdit, QDialog QPlainTextEdit {
    background-color: #FFFFFF;
    color: #2D3748;
    border: 1px solid #E5E5E5;
    border-radius: 6px;
    padding: 8px;
}
QDialog QTabWidget::pane {
    border: 1px solid #E5E5E5;
    background-color: #FFFFFF;
    border-radius: 6px;
}
QDialog QTabBar::tab {
    background-color: #F8F9FA;
    color: #4A5568;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QDialog QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #1A1A1A;
    font-weight: bold;
}
QDialog QPushButton {
    background-color: #F8F9FA;
    color: #2D3748;
    border: 1px solid #E5E5E5;
    padding: 6px 16px;
    border-radius: 6px;
    min-width: 88px;
}
QDialog QPushButton:hover {
    background-color: #E2E8F0;
    border-color: #CBD5E0;
}
"""


def dialog_stylesheet(*, dark: bool) -> str:
    return DIALOG_DARK if dark else DIALOG_LIGHT


def chrome_stylesheet(*, dark: bool) -> str:
    """Message boxes + modal dialogs (theme-matched)."""
    return message_box_stylesheet(dark=dark) + dialog_stylesheet(dark=dark)


def mode_accent_style(mode: str) -> str:
    color = MODE_ACCENTS.get(mode, "#7f8c8d")
    return f"border-left: 4px solid {color}; padding-left: 8px;"
