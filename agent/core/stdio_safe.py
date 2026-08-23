"""Windows-safe stdio and console text (cp1252 / MCP stdio hosts)."""
from __future__ import annotations

import os
import sys


class _NullTextStream:
    """No-op stream for frozen GUI builds where stdout/stderr are None."""

    encoding = "utf-8"

    def write(self, text: str) -> int:
        return len(text or "")

    def flush(self) -> None:
        return None

    @property
    def buffer(self):
        return self


_NULL_STREAM = _NullTextStream()


def configure_stdio_utf8() -> None:
    """Prefer UTF-8 on stdout/stderr so emoji and MCP logs do not crash."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def mcp_stdio_host_active() -> bool:
    """True when Aquila MCP server uses stdio (stdout reserved for JSON-RPC)."""
    return os.getenv("AQUILA_STDIO_MCP_HOST", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def human_output_stream():
    """Stream for Rich console and progress text (stderr under MCP stdio host)."""
    if mcp_stdio_host_active() and sys.stderr is not None:
        return sys.stderr
    if sys.stdout is not None:
        return sys.stdout
    if sys.stderr is not None:
        return sys.stderr
    return _NULL_STREAM


def human_print(*args, **kwargs) -> None:
    """Print progress lines without breaking MCP stdio JSON on stdout."""
    kwargs.setdefault("file", human_output_stream())
    print(*args, **kwargs)


def stdout_supports_unicode() -> bool:
    stream = sys.stdout if sys.stdout is not None else human_output_stream()
    enc = getattr(stream, "encoding", None) or "utf-8"
    try:
        "\u26a1".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError, AttributeError):
        return False


def console_safe(text: str) -> str:
    """Strip/replace characters the active stdout encoding cannot represent."""
    if stdout_supports_unicode():
        return text
    return text.encode("ascii", errors="replace").decode("ascii")


def safe_stdout_write(text: str) -> None:
    if not text:
        return
    stream = human_output_stream()
    if stream is None:
        return
    try:
        enc = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(enc, errors="replace").decode(enc))
    except Exception:
        try:
            buf = getattr(stream, "buffer", None)
            if buf is not None:
                buf.write(text.encode("utf-8", errors="replace"))
            else:
                stream.write(console_safe(text))
        except Exception:
            try:
                stream.write(console_safe(text))
            except Exception:
                return
    try:
        stream.flush()
    except Exception:
        pass
