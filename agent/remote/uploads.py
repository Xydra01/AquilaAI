"""Short-lived attachment cache for the Remote Companion.

Uploaded files are parsed once via ``file_parser.process_local_attachments``
into ``(text_chunks, image_payloads)`` and stashed under an opaque
``upload_token``. Chat/task payloads reference the token instead of re-sending
bytes. Entries expire so the cache cannot grow without bound.
"""
from __future__ import annotations

import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

# token -> {"text_chunks", "image_payloads", "file_names", "created_at"}
_cache: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()

# Tokens live for an hour; long enough to attach then send.
_TTL_SECONDS = 60 * 60


def _prune(now: Optional[float] = None) -> None:
    now = now if now is not None else time.time()
    with _lock:
        stale = [k for k, v in _cache.items() if now - v.get("created_at", 0) > _TTL_SECONDS]
        for k in stale:
            _cache.pop(k, None)


def store_files(named_bytes: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Parse uploaded files and cache the result under a fresh upload token.

    ``named_bytes`` is a list of ``(file_name, content_bytes)``. Returns
    ``{"upload_token", "file_names", "has_images"}``.
    """
    from agent import file_parser

    _prune()
    file_names: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aquila_upload_") as tmp:
        tmp_dir = Path(tmp)
        paths: list[str] = []
        for name, content in named_bytes:
            safe = Path(name or "file").name or "file"
            dest = tmp_dir / safe
            # Avoid clobbering duplicate names within one upload.
            counter = 1
            while dest.exists():
                dest = tmp_dir / f"{dest.stem}_{counter}{dest.suffix}"
                counter += 1
            dest.write_bytes(content)
            paths.append(str(dest))
            file_names.append(dest.name)
        text_chunks, image_payloads = file_parser.process_local_attachments(paths)

    token = secrets.token_urlsafe(18)
    with _lock:
        _cache[token] = {
            "text_chunks": text_chunks,
            "image_payloads": image_payloads,
            "file_names": file_names,
            "created_at": time.time(),
        }
    return {
        "upload_token": token,
        "file_names": file_names,
        "has_images": bool(image_payloads),
    }


def resolve_tokens(tokens: Optional[list[str]]) -> tuple[list[str], list]:
    """Merge cached payloads for the given tokens into ``(text_chunks, images)``."""
    _prune()
    text_chunks: list[str] = []
    image_payloads: list = []
    for token in tokens or []:
        with _lock:
            entry = _cache.get(token)
        if not entry:
            continue
        text_chunks.extend(entry.get("text_chunks") or [])
        image_payloads.extend(entry.get("image_payloads") or [])
    return text_chunks, image_payloads


def pop_tokens(tokens: Optional[list[str]]) -> tuple[list[str], list]:
    """Like :func:`resolve_tokens` but consumes the entries."""
    text_chunks, image_payloads = resolve_tokens(tokens)
    with _lock:
        for token in tokens or []:
            _cache.pop(token, None)
    return text_chunks, image_payloads


def clear() -> None:
    with _lock:
        _cache.clear()
