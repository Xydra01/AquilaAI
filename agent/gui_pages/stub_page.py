"""Placeholder pages for modes not yet fully implemented."""
from PySide6.QtWidgets import QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from gui_pages.base import BaseModePage


class StubModePage(BaseModePage):
  def __init__(self, main_window, title: str, description: str, mode: str, mode_label: str):
    super().__init__(main_window)
    self.MODE = mode
    self.MODE_LABEL = mode_label
    layout = QVBoxLayout(self)
    heading = QLabel(title)
    heading.setAlignment(Qt.AlignCenter)
    heading.setStyleSheet("font-size: 22px; font-weight: bold; margin: 40px;")
    body = QLabel(description)
    body.setWordWrap(True)
    body.setAlignment(Qt.AlignCenter)
    body.setStyleSheet("font-size: 14px; color: #7f8c8d; margin: 20px 60px;")
    layout.addStretch()
    layout.addWidget(heading)
    layout.addWidget(body)
    layout.addStretch()
