"""Display-only formatting for Aquila GUI (does not alter LLM context)."""
from __future__ import annotations

import html
import json
import re
from json import JSONDecodeError

import markdown

_MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "nl2br"]

_STEP_HEADER_RE = re.compile(r"^---\s*(.+?)\s*---\s*$", re.MULTILINE)
_TOOL_HEADER_RE = re.compile(r"^Tool '([^']+)' result:\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def _markdown_to_html(text: str) -> str:
    if not (text or "").strip():
        return ""
    return markdown.markdown(text, extensions=_MARKDOWN_EXTENSIONS)


def pretty_json_text(raw: str) -> str | None:
    """Return indented JSON string if raw parses, else None."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except JSONDecodeError:
        return None
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _json_blocks_to_html(text: str) -> str:
    """Replace top-level `{...}` spans with pretty-printed HTML blocks."""
    out: list[str] = []
    idx = 0
    n = len(text)
    while idx < n:
        if text[idx] == "{":
            try:
                _obj, end = json.JSONDecoder().raw_decode(text, idx)
                pretty = pretty_json_text(text[idx:end])
                if pretty:
                    out.append(
                        '<pre class="json-block"><code>'
                        f"{html.escape(pretty)}</code></pre>"
                    )
                    idx = end
                    continue
            except JSONDecodeError:
                pass
        next_brace = text.find("{", idx + 1)
        if next_brace < 0:
            chunk = text[idx:]
            idx = n
        else:
            chunk = text[idx:next_brace]
            idx = next_brace
        if chunk:
            out.append(_markdown_to_html(chunk))
    return "".join(out) if out else _markdown_to_html(text)


def _fences_to_html(text: str) -> str:
    parts: list[str] = []
    last = 0
    for match in _FENCE_RE.finditer(text):
        before = text[last : match.start()]
        if before.strip():
            parts.append(_json_blocks_to_html(before))
        lang = (match.group(1) or "").lower()
        body = match.group(2)
        if lang in ("json", ""):
            pretty = pretty_json_text(body)
            if pretty:
                body = pretty
        parts.append(
            '<pre class="code-block"><code>'
            f"{html.escape(body.rstrip())}</code></pre>"
        )
        last = match.end()
    tail = text[last:]
    if tail.strip():
        parts.append(_json_blocks_to_html(tail))
    return "".join(parts) if parts else _json_blocks_to_html(text)


def format_ledger_html(raw: str) -> str:
    """Turn execution-log plain text into readable HTML."""
    if not (raw or "").strip():
        return "<p class='muted'>Waiting for agent activity…</p>"

    text = raw.replace("\r\n", "\n")
    text = _STEP_HEADER_RE.sub(
        r'<h3 class="step-header">\1</h3>',
        text,
    )
    text = _TOOL_HEADER_RE.sub(
        r'<div class="tool-label">Tool <code>\1</code> result</div>',
        text,
    )
    body = _fences_to_html(text)
    return f'<div class="ledger-root">{body}</div>'


def format_user_message_html(mode_label: str, prompt: str) -> str:
    safe_mode = html.escape(mode_label or "Chat")
    safe_prompt = html.escape(prompt or "")
    safe_prompt = safe_prompt.replace("\n", "<br>")
    return (
        f'<div class="msg user">'
        f'<span class="msg-label">User ({safe_mode})</span>'
        f'<div class="msg-body">{safe_prompt}</div></div>'
    )


def format_attachment_notice_html(
    file_names: list[str],
    *,
    text_chunk_count: int = 0,
    image_count: int = 0,
) -> str:
    """Visible confirmation that file attachments will be sent with the next message."""
    if not file_names and text_chunk_count == 0 and image_count == 0:
        return ""
    parts: list[str] = []
    if file_names:
        names = ", ".join(html.escape(n) for n in file_names[:8])
        if len(file_names) > 8:
            names += f" (+{len(file_names) - 8} more)"
        parts.append(f"Files: {names}")
    if text_chunk_count:
        parts.append(
            f"{text_chunk_count} text chunk(s) included in model context"
        )
    if image_count:
        parts.append(f"{image_count} image(s) sent to vision")
    detail = " · ".join(parts)
    return (
        '<div class="msg user attachment-notice" style="margin-top:-6px;">'
        '<div class="msg-body" style="font-size:10pt; opacity:0.9;">'
        f"📎 <b>Attachments</b> — {detail}"
        "</div></div>"
    )


def format_assistant_message_html(text: str) -> str:
    body = _fences_to_html(text or "")
    return (
        '<div class="msg assistant">'
        '<span class="msg-label">🦅 Aquila</span>'
        f'<div class="msg-body">{body}</div></div>'
    )


def format_system_message_html(text: str) -> str:
    safe = html.escape(text or "")
    safe = safe.replace("\n", "<br>")
    return (
        '<div class="msg system"><span class="msg-label">System</span>'
        f'<div class="msg-body">{safe}</div></div>'
    )


def format_sleep_cycle_html(text: str) -> str:
    body = _fences_to_html(text or "")
    return (
        '<div class="msg system">'
        '<span class="msg-label">🧠 Sleep cycle</span>'
        f'<div class="msg-body">{body}</div></div>'
    )
