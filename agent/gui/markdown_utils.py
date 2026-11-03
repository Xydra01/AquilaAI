"""Helpers for rendering markdown in Qt widgets."""
from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"(```[\s\S]*?```)")
_INLINE_CODE_RE = re.compile(r"(`[^`\n]+`)")


def escape_markdown_for_qt(text: str) -> str:
    """Escape angle brackets so QTextEdit.setMarkdown() does not treat them as HTML.

    Plan text often includes placeholders like ``add <habit>``; Qt's markdown
    renderer interprets ``<habit>`` as an unknown HTML tag and hides the rest of
    the line. Code spans and fenced blocks are left untouched.
    """
    if not text:
        return text

    def _escape_plain(segment: str) -> str:
        return segment.replace("<", "&lt;").replace(">", "&gt;")

    out: list[str] = []
    for i, fence_part in enumerate(_CODE_FENCE_RE.split(text)):
        if i % 2 == 1:
            out.append(fence_part)
            continue
        for j, inline_part in enumerate(_INLINE_CODE_RE.split(fence_part)):
            if j % 2 == 1:
                out.append(inline_part)
            else:
                out.append(_escape_plain(inline_part))
    return "".join(out)
