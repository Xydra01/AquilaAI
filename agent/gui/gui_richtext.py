"""Rich-text panel styling and chat stream helpers for PySide6."""
from __future__ import annotations

from PySide6.QtGui import QTextCursor, QTextOption
from PySide6.QtWidgets import QTextEdit

from .gui_formatting import (
    ASSISTANT_STREAM_SHELL_CLOSE,
    ASSISTANT_STREAM_SHELL_OPEN,
    format_assistant_body_html,
    format_assistant_message_html,
)

# Pixels/lines from bottom treated as "following" the live tail.
_SCROLL_BOTTOM_THRESHOLD = 12

_CHAT_CSS_DARK = """
body { font-family: 'Inter', 'Roboto', 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 11pt; line-height: 1.6; color: #E8E8E8; background: #1E1E1E; margin: 16px; }
.msg { margin: 16px 0; padding: 16px; border-radius: 8px; }
.msg + .msg { margin-top: 16px; }
.msg.user { background: #252526; border-left: 4px solid #3794FF; }
.msg.assistant { background: transparent; padding-left: 20px; border-left: 4px solid #4CAF50; }
.msg.system { background: #33302A; border-left: 4px solid #F44336; color: #D4D4D4; }
.msg-label { font-weight: 600; display: block; margin-bottom: 8px; color: #9CDCFE; font-size: 10pt; text-transform: uppercase; letter-spacing: 0.5px; }
.msg-body { margin: 0; }
.msg-body p { margin: 0.5em 0; }
.msg-body ul, .msg-body ol { margin: 0.5em 0 0.5em 1.5em; padding-left: 0; }
.msg-body h1, .msg-body h2, .msg-body h3 { margin: 1em 0 0.5em; color: #3794FF; font-weight: 600; }
pre, pre.code-block, pre.json-block {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace; font-size: 10pt;
  background: #151515; color: #D4D4D4; padding: 12px; border-radius: 8px;
  border: 1px solid #333333; margin: 12px 0; white-space: pre-wrap; line-height: 1.4;
}
code { font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; background: #2D2D30; padding: 2px 6px; border-radius: 4px; color: #CE9178; }
a { color: #3794FF; text-decoration: none; }
a:hover { text-decoration: underline; }
table { border-collapse: collapse; margin: 12px 0; width: 100%; }
th, td { border: 1px solid #333333; padding: 8px 12px; text-align: left; }
th { background: #252526; font-weight: 600; }
"""

_CHAT_CSS_LIGHT = """
body { font-family: 'Inter', 'Roboto', 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 11pt; line-height: 1.6; color: #1A1A1A; background: #F8F9FA; margin: 16px; }
.msg { margin: 16px 0; padding: 16px; border-radius: 8px; }
.msg + .msg { margin-top: 16px; }
.msg.user { background: #FFFFFF; border-left: 4px solid #0066FF; border: 1px solid #E5E5E5; border-left-width: 4px; }
.msg.assistant { background: transparent; padding-left: 20px; border-left: 4px solid #28A745; }
.msg.system { background: #FFF8E6; border-left: 4px solid #B45309; }
.msg-label { font-weight: 600; display: block; margin-bottom: 8px; color: #0066FF; font-size: 10pt; text-transform: uppercase; letter-spacing: 0.5px; }
.msg-body p { margin: 0.5em 0; }
.msg-body ul, .msg-body ol { margin: 0.5em 0 0.5em 1.5em; padding-left: 0; }
.msg-body h1, .msg-body h2, .msg-body h3 { margin: 1em 0 0.5em; color: #0066FF; font-weight: 600; }
pre, pre.code-block, pre.json-block {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace; font-size: 10pt;
  background: #F0F2F5; color: #24292F; padding: 12px; border-radius: 8px;
  border: 1px solid #E5E5E5; margin: 12px 0; white-space: pre-wrap; line-height: 1.4;
}
code { font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; background: #EFF1F3; padding: 2px 6px; border-radius: 4px; color: #A31515; }
a { color: #0066FF; text-decoration: none; }
a:hover { text-decoration: underline; }
table { border-collapse: collapse; margin: 12px 0; width: 100%; }
th, td { border: 1px solid #E5E5E5; padding: 8px 12px; text-align: left; }
th { background: #F0F2F5; font-weight: 600; }
"""

_LEDGER_CSS_DARK = """
body { font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace; font-size: 10pt; line-height: 1.5; color: #D4D4D4; background: #1E1E1E; }
.ledger-root { padding: 8px 16px; }
h3.step-header { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12pt; color: #3794FF; margin: 16px 0 8px; font-weight: 600; border-bottom: 1px solid #333333; padding-bottom: 4px; }
.tool-label { font-family: 'Inter', 'Segoe UI', sans-serif; color: #DCDCAA; margin: 12px 0 4px; font-size: 10pt; font-weight: 500; }
.tool-label code { color: #9CDCFE; background: #252526; padding: 2px 6px; border-radius: 4px; font-size: 9.5pt; }
p { margin: 0.5em 0; font-family: 'Inter', 'Segoe UI', sans-serif; }
pre, pre.code-block, pre.json-block {
  background: #151515; border: 1px solid #333333; border-radius: 8px;
  padding: 12px; margin: 8px 0; white-space: pre-wrap; line-height: 1.4;
}
.json-block { border-left: 3px solid #569CD6; }
.muted { color: #858585; font-style: italic; }
"""

_LEDGER_CSS_LIGHT = """
body { font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace; font-size: 10pt; line-height: 1.5; color: #24292F; background: #FFFFFF; }
.ledger-root { padding: 8px 16px; }
h3.step-header { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12pt; color: #0066FF; margin: 16px 0 8px; font-weight: 600; border-bottom: 1px solid #E5E5E5; padding-bottom: 4px; }
.tool-label { font-family: 'Inter', 'Segoe UI', sans-serif; color: #92400E; margin: 12px 0 4px; font-size: 10pt; font-weight: 500; }
.tool-label code { color: #0969DA; background: #F0F2F5; padding: 2px 6px; border-radius: 4px; font-size: 9.5pt; }
p { margin: 0.5em 0; font-family: 'Inter', 'Segoe UI', sans-serif; }
pre, pre.code-block, pre.json-block {
  background: #F0F2F5; border: 1px solid #E5E5E5; border-radius: 8px;
  padding: 12px; margin: 8px 0; white-space: pre-wrap; line-height: 1.4;
}
.json-block { border-left: 3px solid #0969DA; }
.muted { color: #656D76; font-style: italic; }
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

    def insert_html_smart(self, html: str) -> None:
        follow = self._stick_to_bottom or self._is_at_bottom()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        self.setTextCursor(cursor)
        if follow:
            self._scroll_to_bottom()


_THINKING_CSS_DARK = """
body { font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; font-size: 9.5pt; line-height: 1.5; color: #A0A0A0; background: #151515; }
"""

_THINKING_CSS_LIGHT = """
body { font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; font-size: 9.5pt; line-height: 1.5; color: #656D76; background: #F0F2F5; }
"""


def apply_thinking_panel_style(widget, *, dark: bool) -> None:
    """Style the collapsible native thinking pane (QTextEdit)."""
    css = _THINKING_CSS_DARK if dark else _THINKING_CSS_LIGHT
    widget.setReadOnly(True)
    widget.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    widget.document().setDefaultStyleSheet(css)
    border = "#333333" if dark else "#E5E5E5"
    widget.setStyleSheet(
        f"QTextEdit {{ border: 1px solid {border}; border-radius: 8px; "
        f"background: {'#151515' if dark else '#F0F2F5'}; padding: 8px; }}"
    )


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


def insert_assistant_stream_shell(chat_widget) -> int:
    """Insert labeled assistant bubble open tag; return body stream start position."""
    html = "<br>" + ASSISTANT_STREAM_SHELL_OPEN
    if isinstance(chat_widget, SmartScrollTextEdit):
        chat_widget.insert_html_smart(html)
    else:
        cursor = chat_widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        chat_widget.setTextCursor(cursor)
    chat_widget.setProperty("_stream_has_shell", True)
    return mark_stream_start(chat_widget)


def _maybe_scroll_chat(chat_widget) -> None:
    if isinstance(chat_widget, SmartScrollTextEdit):
        if chat_widget._stick_to_bottom or chat_widget._is_at_bottom():
            chat_widget._scroll_to_bottom()


def finalize_streamed_message(
    chat_widget,
    raw_text: str,
    *,
    html_formatter=None,
) -> None:
    """Replace streamed plain text with rendered markdown/HTML."""
    has_shell = bool(chat_widget.property("_stream_has_shell"))
    start = chat_widget.property("_stream_start_pos")
    if has_shell and start is not None:
        try:
            start = int(start)
        except (TypeError, ValueError):
            start = None
        if start is not None and start >= 0:
            cursor = chat_widget.textCursor()
            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            body = format_assistant_body_html(raw_text)
            cursor.insertHtml(body + ASSISTANT_STREAM_SHELL_CLOSE)
            chat_widget.setTextCursor(cursor)
            chat_widget.setProperty("_stream_start_pos", None)
            chat_widget.setProperty("_stream_has_shell", False)
            _maybe_scroll_chat(chat_widget)
            return

    render = html_formatter or format_assistant_message_html
    if start is None:
        if isinstance(chat_widget, SmartScrollTextEdit):
            chat_widget.append_smart(render(raw_text))
        else:
            chat_widget.append(render(raw_text))
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
    rendered = render(raw_text)
    cursor.insertHtml(rendered)
    chat_widget.setTextCursor(cursor)
    chat_widget.setProperty("_stream_start_pos", None)
    chat_widget.setProperty("_stream_has_shell", False)
    _maybe_scroll_chat(chat_widget)
