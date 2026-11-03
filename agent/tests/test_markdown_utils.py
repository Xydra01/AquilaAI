"""Tests for Qt markdown rendering helpers."""
from __future__ import annotations

from agent.gui.markdown_utils import escape_markdown_for_qt


def test_escape_markdown_for_qt_escapes_angle_brackets_in_prose():
    raw = "- CLI accepts 'add <habit>' command successfully."
    out = escape_markdown_for_qt(raw)
    assert "<habit>" not in out
    assert "&lt;habit&gt;" in out


def test_escape_markdown_for_qt_preserves_inline_code():
    raw = "Use `add <habit>` in the shell."
    out = escape_markdown_for_qt(raw)
    assert out == raw


def test_escape_markdown_for_qt_preserves_fenced_code():
    raw = "Example:\n```python\nif x < 1:\n    pass\n```\nDone."
    out = escape_markdown_for_qt(raw)
    assert "x < 1" in out
    assert "&lt;" not in out.split("```")[1]
