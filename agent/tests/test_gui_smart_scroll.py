"""Tests for SmartScrollTextEdit scroll-follow behavior."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from gui_richtext import SmartScrollTextEdit


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_set_html_smart_follows_bottom_when_stuck(qapp):
    view = SmartScrollTextEdit()
    view.set_html_smart("<p>line 1</p>")
    view.set_html_smart("<p>line 1</p><p>line 2</p><p>line 3</p>")
    bar = view.verticalScrollBar()
    assert bar.maximum() - bar.value() <= 12


def test_set_html_smart_preserves_scroll_when_user_scrolled_up(qapp):
    view = SmartScrollTextEdit()
    view.set_html_smart("<p>" + "<br>body</p>" * 80 + "</p>")
    bar = view.verticalScrollBar()
    bar.setValue(0)
    view._stick_to_bottom = False
    old_val = bar.value()
    view.set_html_smart("<p>" + "<br>more</p>" * 90 + "</p>")
    assert view.verticalScrollBar().value() == old_val
