"""Themed QMessageBox helpers (respect Aquila dark/light mode)."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QDialog, QWidget

from .gui_theme import chrome_stylesheet, message_box_stylesheet


def dark_mode_from_widget(widget: QWidget | None) -> bool:
    w = widget
    while w is not None:
        main_window = getattr(w, "main_window", None)
        if main_window is not None and hasattr(main_window, "dark_mode"):
            return bool(main_window.dark_mode)
        if hasattr(w, "dark_mode"):
            return bool(w.dark_mode)
        w = w.parentWidget()
    return False


def style_message_box(
    box: QMessageBox,
    *,
    parent: QWidget | None = None,
    dark: bool | None = None,
) -> QMessageBox:
    if dark is None:
        dark = dark_mode_from_widget(parent or box.parentWidget())
    box.setStyleSheet(message_box_stylesheet(dark=dark))
    return box


def apply_dialog_theme(
    dialog: QDialog,
    *,
    parent: QWidget | None = None,
    dark: bool | None = None,
) -> QDialog:
    if dark is None:
        dark = dark_mode_from_widget(parent or dialog.parentWidget())
    dialog.setStyleSheet(chrome_stylesheet(dark=dark))
    return dialog


def question(
    parent: QWidget | None,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = (
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    ),
    default: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
) -> QMessageBox.StandardButton:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    box.setDefaultButton(default)
    style_message_box(box, parent=parent)
    return QMessageBox.StandardButton(box.exec())


def warning(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    style_message_box(box, parent=parent)
    box.exec()


def information(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    style_message_box(box, parent=parent)
    box.exec()
