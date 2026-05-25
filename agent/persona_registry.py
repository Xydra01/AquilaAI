"""Per-instance Character AI personas (storage + chat history)."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from instance_registry import instance_dir

MAX_CHAT_TURNS = 40
MAX_CHAT_CHARS = 120_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "persona").lower()).strip("-")
    return slug[:64] or "persona"


@dataclass
class Persona:
    id: str
    display_name: str
    tagline: str = ""
    description: str = ""
    greeting: str = ""
    avatar_relpath: str = ""
    created_at: str = ""
    last_chat_at: str = ""
    build_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        return cls(
            id=str(data.get("id", "")),
            display_name=str(data.get("display_name", "Character")),
            tagline=str(data.get("tagline", "")),
            description=str(data.get("description", "")),
            greeting=str(data.get("greeting", "")),
            avatar_relpath=str(data.get("avatar_relpath", "")),
            created_at=str(data.get("created_at", "")),
            last_chat_at=str(data.get("last_chat_at", "")),
            build_complete=bool(data.get("build_complete", True)),
        )


def personas_root(instance_id: str) -> Path:
    return instance_dir(instance_id) / "personas"


def persona_dir(instance_id: str, persona_id: str) -> Path:
    return personas_root(instance_id) / persona_id


def persona_json_path(instance_id: str, persona_id: str) -> Path:
    return persona_dir(instance_id, persona_id) / "persona.json"


def initialization_path(instance_id: str, persona_id: str) -> Path:
    return persona_dir(instance_id, persona_id) / "initialization.md"


def user_preferences_path(instance_id: str, persona_id: str) -> Path:
    return persona_dir(instance_id, persona_id) / "user_preferences.md"


def chat_history_path(instance_id: str, persona_id: str) -> Path:
    return persona_dir(instance_id, persona_id) / "chat_history.json"


def sources_dir(instance_id: str, persona_id: str) -> Path:
    return persona_dir(instance_id, persona_id) / "sources"


def list_personas(instance_id: str) -> list[Persona]:
    root = personas_root(instance_id)
    if not root.is_dir():
        return []
    out: list[Persona] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        p = get_persona(instance_id, child.name)
        if p:
            out.append(p)
    return sorted(out, key=lambda p: p.last_chat_at or p.created_at, reverse=True)


def get_persona(instance_id: str, persona_id: str) -> Persona | None:
    path = persona_json_path(instance_id, persona_id)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return Persona.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        return None


def create_persona(
    instance_id: str,
    display_name: str,
    description: str = "",
    *,
    persona_id: str | None = None,
    build_complete: bool = False,
) -> Persona:
    base = persona_id or _slugify(display_name)
    candidate = base
    n = 1
    while persona_json_path(instance_id, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    now = _now_iso()
    pdir = persona_dir(instance_id, candidate)
    pdir.mkdir(parents=True, exist_ok=True)
    sources_dir(instance_id, candidate).mkdir(exist_ok=True)
    user_preferences_path(instance_id, candidate).write_text(
        "# User preferences\n\n_(The character learns about you over time.)_\n",
        encoding="utf-8",
    )
    chat_history_path(instance_id, candidate).write_text("[]", encoding="utf-8")
    persona = Persona(
        id=candidate,
        display_name=display_name.strip() or "Character",
        description=description.strip(),
        created_at=now,
        last_chat_at=now,
        build_complete=build_complete,
    )
    save_persona(instance_id, persona)
    return persona


def save_persona(instance_id: str, persona: Persona) -> Persona:
    pdir = persona_dir(instance_id, persona.id)
    pdir.mkdir(parents=True, exist_ok=True)
    persona.last_chat_at = persona.last_chat_at or _now_iso()
    with open(persona_json_path(instance_id, persona.id), "w", encoding="utf-8") as f:
        json.dump(persona.to_dict(), f, indent=2)
    return persona


def delete_persona(instance_id: str, persona_id: str) -> bool:
    pdir = persona_dir(instance_id, persona_id)
    if not pdir.exists():
        return False
    import shutil

    shutil.rmtree(pdir, ignore_errors=True)
    return True


def load_initialization_doc(instance_id: str, persona_id: str) -> str:
    path = initialization_path(instance_id, persona_id)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_user_preferences(instance_id: str, persona_id: str) -> str:
    path = user_preferences_path(instance_id, persona_id)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def save_user_preferences(instance_id: str, persona_id: str, text: str) -> None:
    path = user_preferences_path(instance_id, persona_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")


def append_user_preference_note(instance_id: str, persona_id: str, note: str) -> None:
    note = (note or "").strip()
    if not note:
        return
    existing = load_user_preferences(instance_id, persona_id)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = f"\n- ({stamp}) {note}\n"
    save_user_preferences(instance_id, persona_id, existing.rstrip() + block)


def load_chat_history(instance_id: str, persona_id: str) -> list[dict[str, str]]:
    path = chat_history_path(instance_id, persona_id)
    if not path.is_file():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [
                {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
                for m in data
                if isinstance(m, dict) and m.get("content")
            ]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_chat_history(instance_id: str, persona_id: str, messages: list[dict[str, str]]) -> None:
    trimmed = _trim_history(messages)
    path = chat_history_path(instance_id, persona_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, indent=2, ensure_ascii=False)
    persona = get_persona(instance_id, persona_id)
    if persona:
        persona.last_chat_at = _now_iso()
        save_persona(instance_id, persona)


def _trim_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if not messages:
        return []
    out = messages[-MAX_CHAT_TURNS:]
    total = sum(len(m.get("content", "")) for m in out)
    while out and total > MAX_CHAT_CHARS:
        out = out[2:]
        total = sum(len(m.get("content", "")) for m in out)
    return out


def count_user_turns(messages: list[dict[str, str]]) -> int:
    return sum(1 for m in messages if m.get("role") == "user")
