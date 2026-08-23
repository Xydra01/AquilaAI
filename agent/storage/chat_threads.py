"""Per-instance Chat Mode thread storage (titles + message history)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .instance_registry import instance_dir

MAX_CHAT_TURNS = 60
MAX_CHAT_CHARS = 180_000
DEFAULT_THREAD_ID = "thread-default"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "thread").lower()).strip("-")
    return slug[:64] or "thread"


@dataclass
class ChatThread:
    id: str
    title: str
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatThread":
        return cls(
            id=str(data.get("id", DEFAULT_THREAD_ID)),
            title=str(data.get("title", "New chat")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


def chat_threads_root(instance_id: str) -> Path:
    return instance_dir(instance_id) / "chat_threads"


def thread_dir(instance_id: str, thread_id: str) -> Path:
    return chat_threads_root(instance_id) / thread_id


def thread_meta_path(instance_id: str, thread_id: str) -> Path:
    return thread_dir(instance_id, thread_id) / "thread.json"


def thread_history_path(instance_id: str, thread_id: str) -> Path:
    return thread_dir(instance_id, thread_id) / "history.json"


def _safe_title(title_hint: str) -> str:
    text = re.sub(r"\s+", " ", (title_hint or "").strip())
    if not text:
        return "New chat"
    return text[:80]


def _trim_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if not messages:
        return []
    out = messages[-MAX_CHAT_TURNS:]
    total = sum(len(m.get("content", "")) for m in out)
    while out and total > MAX_CHAT_CHARS:
        out = out[2:]
        total = sum(len(m.get("content", "")) for m in out)
    return out


def get_thread(instance_id: str, thread_id: str) -> ChatThread | None:
    path = thread_meta_path(instance_id, thread_id)
    if not path.is_file():
        return None
    try:
        return ChatThread.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def save_thread(instance_id: str, thread: ChatThread) -> ChatThread:
    root = thread_dir(instance_id, thread.id)
    root.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    if not thread.created_at:
        thread.created_at = now
    thread.updated_at = now
    thread_meta_path(instance_id, thread.id).write_text(
        json.dumps(thread.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return thread


def list_threads(instance_id: str) -> list[ChatThread]:
    root = chat_threads_root(instance_id)
    if not root.is_dir():
        return []
    out: list[ChatThread] = []
    for child in root.iterdir():
        if child.is_dir():
            t = get_thread(instance_id, child.name)
            if t:
                out.append(t)
    return sorted(out, key=lambda t: t.updated_at or t.created_at, reverse=True)


def create_thread(instance_id: str, title_hint: str = "", thread_id: str | None = None) -> ChatThread:
    base = thread_id or _slugify(title_hint or "new-chat")
    candidate = base
    idx = 1
    while get_thread(instance_id, candidate) is not None:
        candidate = f"{base}-{idx}"
        idx += 1
    t = ChatThread(id=candidate, title=_safe_title(title_hint))
    save_thread(instance_id, t)
    thread_history_path(instance_id, t.id).write_text("[]", encoding="utf-8")
    return t


def ensure_default_thread(instance_id: str) -> ChatThread:
    existing = get_thread(instance_id, DEFAULT_THREAD_ID)
    if existing:
        return existing
    return create_thread(instance_id, "New chat", thread_id=DEFAULT_THREAD_ID)


def load_thread_history(instance_id: str, thread_id: str) -> list[dict[str, str]]:
    path = thread_history_path(instance_id, thread_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [
                {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
                for m in data
                if isinstance(m, dict) and m.get("content")
            ]
    except Exception:
        pass
    return []


def save_thread_history(instance_id: str, thread_id: str, messages: list[dict[str, str]]) -> None:
    trimmed = _trim_history(messages)
    root = thread_dir(instance_id, thread_id)
    root.mkdir(parents=True, exist_ok=True)
    thread_history_path(instance_id, thread_id).write_text(
        json.dumps(trimmed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    thread = get_thread(instance_id, thread_id) or ChatThread(id=thread_id, title="New chat")
    if trimmed and thread.title == "New chat":
        first_user = next((m.get("content", "") for m in trimmed if m.get("role") == "user"), "")
        if first_user.strip():
            thread.title = _safe_title(first_user)
    save_thread(instance_id, thread)


def regenerate_last_turn(instance_id: str, thread_id: str) -> tuple[list[dict[str, str]], str]:
    """Drop last assistant turn and return (updated_history, prompt_to_resend)."""
    hist = load_thread_history(instance_id, thread_id)
    if not hist:
        return [], ""
    prompt = ""
    if hist and hist[-1].get("role") == "assistant":
        hist.pop()
    if hist and hist[-1].get("role") == "user":
        prompt = hist[-1].get("content", "")
    save_thread_history(instance_id, thread_id, hist)
    return hist, prompt


def edit_last_user_turn(instance_id: str, thread_id: str, new_text: str) -> list[dict[str, str]]:
    """
    Replace the most recent user turn text and truncate all turns after it.
    """
    hist = load_thread_history(instance_id, thread_id)
    if not hist:
        return []
    idx = -1
    for i in range(len(hist) - 1, -1, -1):
        if hist[i].get("role") == "user":
            idx = i
            break
    if idx < 0:
        return hist
    edited = list(hist[: idx + 1])
    edited[idx] = {"role": "user", "content": (new_text or "").strip()}
    save_thread_history(instance_id, thread_id, edited)
    return edited


def fork_thread(
    instance_id: str, source_thread_id: str, *, upto_index: int | None = None, title_hint: str = ""
) -> ChatThread:
    src = load_thread_history(instance_id, source_thread_id)
    if upto_index is not None:
        src = src[: max(0, upto_index + 1)]
    t = create_thread(instance_id, title_hint or "Forked chat")
    save_thread_history(instance_id, t.id, src)
    return t

