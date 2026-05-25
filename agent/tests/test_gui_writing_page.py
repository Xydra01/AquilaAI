import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from gui_pages.writing_page import WritingPage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_writing_page_mode_flag(qapp, qtbot):
    import gui

    window = gui.AquilaOS()
    qtbot.addWidget(window)
    page = WritingPage(window)
    qtbot.addWidget(page)
    assert page.mode_flag() == "writing"
