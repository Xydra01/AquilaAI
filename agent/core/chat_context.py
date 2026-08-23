"""Utilities for parsing @context references in chat text."""
from __future__ import annotations

import re
from pathlib import Path


_AT_TOKEN_RE = re.compile(r"(?<!\w)@(\S+)")


def parse_at_context(text: str, base_dir: str | None = None) -> tuple[str, list[str], list[str]]:
    """
    Parse @tokens from user text.
    - @https://... => URL context
    - @relative/or/absolute/path => local file/folder context
    """
    raw = text or ""
    base = Path(base_dir).resolve() if base_dir else Path.cwd()
    files: list[str] = []
    urls: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        token = (match.group(1) or "").strip()
        if not token:
            return match.group(0)
        if token.startswith(("http://", "https://")):
            urls.append(token)
            return token
        p = Path(token)
        if not p.is_absolute():
            p = (base / p).resolve()
        if p.exists():
            files.append(str(p))
            return p.name
        return match.group(0)

    cleaned = _AT_TOKEN_RE.sub(_replace, raw)
    # De-dup while preserving order.
    files = list(dict.fromkeys(files))
    urls = list(dict.fromkeys(urls))
    return cleaned, files, urls
