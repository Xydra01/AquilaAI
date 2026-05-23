"""Rich-text panel styling and chat stream helpers for PySide6."""
from __future__ import annotations

from PySide6.QtGui import QTextCursor, QTextOption
from PySide6.QtWidgets import QTextEdit

from gui_formatting import format_assistant_message_html

# Pixels/lines from bottom treated as "following" the live tail.
_SCROLL_BOTTOM_THRESHOLD = 12

_CHAT_CSS_DARK = """
body { font-family: 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 11pt; line-height: 1.45; color: #e8e8e8; }
.msg { margin: 10px 0; padding: 10px 12px; border-radius: 8px; }
.msg.user { background: #2a3f5f; border-left: 3px solid #4a9eff; }
.msg.assistant { background: #2d2d30; border-left: 3px solid #4ec9b0; }
.msg.system { background: #33302a; border-left: 3px solid #dcdcaa; color: #d4d4d4; }
.msg-label { font-weight: 600; display: block; margin-bottom: 6px; color: #9cdcfe; }
.msg-body { margin: 0; }
.msg-body p { margin: 0.4em 0; }
.msg-body ul, .msg-body ol { margin: 0.4em 0 0.4em 1.2em; }
.msg-body h1, .msg-body h2, .msg-body h3 { margin: 0.6em 0 0.3em; color: #4ec9b0; }
pre, pre.code-block, pre.json-block {
  font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 10pt;
  background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 6px;
  border: 1px solid #3e3e42; margin: 8px 0; white-space: pre-wrap;
}
code { font-family: 'Cascadia Code', 'Consolas', monospace; background: #3c3c3c; padding: 1px 4px; border-radius: 3px; }
a { color: #4a9eff; }
table { border-collapse: collapse; margin: 8px 0; }
th, td { border: 1px solid #3e3e42; padding: 4px 8px; }
"""

_CHAT_CSS_LIGHT = """
body { font-family: 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 11pt; line-height: 1.45; color: #1a1a1a; }
.msg { margin: 10px 0; padding: 10px 12px; border-radius: 8px; }
.msg.user { background: #e8f0fe; border-left: 3px solid #1a73e8; }
.msg.assistant { background: #f5f5f5; border-left: 3px solid #0d9488; }
.msg.system { background: #fff8e6; border-left: 3px solid #b45309; }
.msg-label { font-weight: 600; display: block; margin-bottom: 6px; color: #1a56db; }
.msg-body p { margin: 0.4em 0; }
.msg-body h1, .msg-body h2, .msg-body h3 { margin: 0.6em 0 0.3em; color: #0d9488; }
pre, pre.code-block, pre.json-block {
  font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 10pt;
  background: #f6f8fa; color: #24292f; padding: 10px; border-radius: 6px;
  border: 1px solid #d0d7de; margin: 8px 0; white-space: pre-wrap;
}
code { font-family: 'Cascadia Code', 'Consolas', monospace; background: #eff1f3; padding: 1px 4px; border-radius: 3px; }
a { color: #1a73e8; }
"""

_LEDGER_CSS_DARK = """
body { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 10pt; line-height: 1.35; color: #d4d4d4; }
.ledger-root { padding: 4px; }
h3.step-header { font-family: 'Segoe UI', sans-serif; font-size: 11pt; color: #4ec9b0; margin: 14px 0 6px; font-weight: 600; }
.tool-label { font-family: 'Segoe UI', sans-serif; color: #dcdcaa; margin: 10px 0 4px; }
.tool-label code { color: #9cdcfe; background: #2d2d30; }
p { margin: 0.35em 0; font-family: 'Segoe UI', sans-serif; }
pre, pre.code-block, pre.json-block {
  background: #1e1e1e; border: 1px solid #3e3e42; border-radius: 6px;
  padding: 10px; margin: 6px 0; white-space: pre-wrap;
}
.json-block { border-left: 3px solid #569cd6; }
.muted { color: #858585; font-style: italic; }
"""

_LEDGER_CSS_LIGHT = """
body { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 10pt; line-height: 1.35; color: #24292f; }
.ledger-root { padding: 4px; }
h3.step-header { font-family: 'Segoe UI', sans-serif; font-size: 11pt; color: #0d9488; margin: 14px 0 6px; }
.tool-label { font-family: 'Segoe UI', sans-serif; color: #92400e; margin: 10px 0 4px; }
pre, pre.code-block, pre.json-block {
  background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
  padding: 10px; margin: 6px 0; white-space: pre-wrap;
}
.json-block { border-left: 3px solid #0969da; }
.muted { color: #656d76; font-style: italic; }
"""


class SmartScrollTextEdit(QTextEdit):
    """
    QTextEdit that follows new content at the bottom unless the user scrolled up.
    setHtml() normally jumps to the top; this widget preserves scroll intent.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stick_to_bottom = True
        self._programmatic_scroll = False
        self.verticalScrollBar().valueChanged.connect(self._on_scrollbar_changed)

    def _on_scrollbar_changed(self, _value: int) -> None:
        if self._programmatic_scroll:
            return
        self._stick_to_bottom = self._is_at_bottom()

    def _is_at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        if bar.maximum() <= 0:
            return True
        return (bar.maximum() - bar.value()) <= _SCROLL_BOTTOM_THRESHOLD

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        self._programmatic_scroll = True
        bar.setValue(bar.maximum())
        self._programmatic_scroll = False
        self._stick_to_bottom = True

    def reset_scroll_follow(self) -> None:
        """Re-enable tail-following (e.g. new task or cleared view)."""
        self._stick_to_bottom = True
        self._scroll_to_bottom()

    def set_html_smart(self, html: str) -> None:
        """Replace document HTML without yanking scroll if the user scrolled up."""
        bar = self.verticalScrollBar()
        old_max = bar.maximum()
        old_val = bar.value()
        ratio = (old_val / old_max) if old_max > 0 else 1.0
        follow = self._stick_to_bottom or self._is_at_bottom()

        self.setHtml(html)

        bar = self.verticalScrollBar()
        self._programmatic_scroll = True
        if follow:
            bar.setValue(bar.maximum())
            self._stick_to_bottom = True
        else:
            new_max = bar.maximum()
            bar.setValue(int(ratio * new_max) if new_max > 0 else 0)
            self._stick_to_bottom = False
        self._programmatic_scroll = False

    def append_smart(self, text: str) -> None:
        follow = self._stick_to_bottom or self._is_at_bottom()
        super().append(text)
        if follow:
            self._scroll_to_bottom()

    def insert_text_smart(self, text: str) -> None:
        follow = self._stick_to_bottom or self._is_at_bottom()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        if follow:
            self._scroll_to_bottom()


def apply_panel_style(widget, panel: str, *, dark: bool) -> None:
    """Attach document CSS and sensible defaults to a read-only QTextEdit."""
    css = {
        ("chat", True): _CHAT_CSS_DARK,
        ("chat", False): _CHAT_CSS_LIGHT,
        ("ledger", True): _LEDGER_CSS_DARK,
        ("ledger", False): _LEDGER_CSS_LIGHT,
    }.get((panel, dark), _CHAT_CSS_DARK)
    widget.setReadOnly(True)
    widget.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    widget.document().setDefaultStyleSheet(css)


def mark_stream_start(chat_widget) -> int:
    """Record cursor position where streamed assistant text begins."""
    cursor = chat_widget.textCursor()
    cursor.movePosition(QTextCursor.End)
    pos = cursor.position()
    chat_widget.setProperty("_stream_start_pos", pos)
    return pos


def _maybe_scroll_chat(chat_widget) -> None:
    if isinstance(chat_widget, SmartScrollTextEdit):
        if chat_widget._stick_to_bottom or chat_widget._is_at_bottom():
            chat_widget._scroll_to_bottom()


def finalize_streamed_message(chat_widget, raw_text: str) -> None:
    """Replace streamed plain text with rendered markdown/HTML."""
    start = chat_widget.property("_stream_start_pos")
    if start is None:
        if isinstance(chat_widget, SmartScrollTextEdit):
            chat_widget.append_smart(format_assistant_message_html(raw_text))
        else:
            chat_widget.append(format_assistant_message_html(raw_text))
        chat_widget.setProperty("_stream_start_pos", None)
        _maybe_scroll_chat(chat_widget)
        return
    try:
        start = int(start)
    except (TypeError, ValueError):
        start = None
    cursor = chat_widget.textCursor()
    if start is not None and start >= 0:
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
    rendered = format_assistant_message_html(raw_text)
    cursor.insertHtml(rendered)
    chat_widget.setTextCursor(cursor)
    chat_widget.setProperty("_stream_start_pos", None)
    _maybe_scroll_chat(chat_widget)
