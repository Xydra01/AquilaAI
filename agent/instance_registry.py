"""Aquila OS 3.4 — specialized agent instances (profiles, workspace summaries)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace_paths import agent_data_path


def _instances_root() -> Path:
    return agent_data_path("Agent-Instances")


def _active_file() -> Path:
    return _instances_root() / "active.json"
DEFAULT_INSTANCE_ID = "default"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "instance").lower()).strip("-")
    return slug[:64] or "instance"


@dataclass
class AquilaInstance:
    id: str
    display_name: str
    specialty: str = ""
    default_mode: str = "chat"
    prompt_addendum: str = ""
    ollama_model: str | None = None
    auto_apply_patches: bool | None = None
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    last_opened_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AquilaInstance":
        return cls(
            id=str(data.get("id", DEFAULT_INSTANCE_ID)),
            display_name=str(data.get("display_name", "Default")),
            specialty=str(data.get("specialty", "")),
            default_mode=str(data.get("default_mode", "chat")),
            prompt_addendum=str(data.get("prompt_addendum", "")),
            ollama_model=data.get("ollama_model"),
            auto_apply_patches=data.get("auto_apply_patches"),
            mcp_servers=list(data.get("mcp_servers") or []),
            created_at=str(data.get("created_at", "")),
            last_opened_at=str(data.get("last_opened_at", "")),
        )


def instance_dir(instance_id: str) -> Path:
    return _instances_root() / instance_id


def profile_path(instance_id: str) -> Path:
    return instance_dir(instance_id) / "profile.json"


def workspace_summary_path(instance_id: str) -> Path:
    return instance_dir(instance_id) / "workspace_summary.md"


def conversation_archive_path(instance_id: str) -> Path:
    return instance_dir(instance_id) / "conversation_archive.jsonl"


def ensure_instances_root() -> None:
    _instances_root().mkdir(parents=True, exist_ok=True)


def save_instance(instance: AquilaInstance) -> AquilaInstance:
    ensure_instances_root()
    inst_dir = instance_dir(instance.id)
    inst_dir.mkdir(parents=True, exist_ok=True)
    instance.last_opened_at = _now_iso()
    if not instance.created_at:
        instance.created_at = instance.last_opened_at
    with open(profile_path(instance.id), "w", encoding="utf-8") as f:
        json.dump(instance.to_dict(), f, indent=2)
    return instance


def get_instance(instance_id: str) -> AquilaInstance | None:
    path = profile_path(instance_id)
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return AquilaInstance.from_dict(json.load(f))


def list_instances() -> list[AquilaInstance]:
    ensure_instances_root()
    out: list[AquilaInstance] = []
    for child in sorted(_instances_root().iterdir()):
        if not child.is_dir():
            continue
        inst = get_instance(child.name)
        if inst:
            out.append(inst)
    return sorted(out, key=lambda i: i.last_opened_at or i.created_at, reverse=True)


def create_instance(
    display_name: str,
    specialty: str = "",
    default_mode: str = "chat",
    prompt_addendum: str = "",
    ollama_model: str | None = None,
    instance_id: str | None = None,
) -> AquilaInstance:
    base_id = instance_id or _slugify(display_name)
    candidate = base_id
    n = 1
    while get_instance(candidate) is not None:
        candidate = f"{base_id}-{n}"
        n += 1
    now = _now_iso()
    inst = AquilaInstance(
        id=candidate,
        display_name=display_name,
        specialty=specialty,
        default_mode=default_mode,
        prompt_addendum=prompt_addendum,
        ollama_model=ollama_model,
        created_at=now,
        last_opened_at=now,
    )
    save_instance(inst)
    workspace_summary_path(inst.id).write_text(
        f"# Workspace summary — {display_name}\n\n_(No steps completed yet.)_\n",
        encoding="utf-8",
    )
    return inst


def ensure_default_instance() -> AquilaInstance:
    existing = get_instance(DEFAULT_INSTANCE_ID)
    if existing:
        return existing
    return create_instance(
        display_name="Default Aquila",
        specialty="General-purpose local agent",
        default_mode="chat",
        instance_id=DEFAULT_INSTANCE_ID,
    )


def get_active_instance_id() -> str:
    ensure_instances_root()
    ensure_default_instance()
    active = _active_file()
    if active.is_file():
        try:
            data = json.loads(active.read_text(encoding="utf-8"))
            iid = str(data.get("instance_id", DEFAULT_INSTANCE_ID))
            if get_instance(iid):
                return iid
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_INSTANCE_ID


def set_active_instance_id(instance_id: str) -> None:
    ensure_instances_root()
    if not get_instance(instance_id):
        raise ValueError(f"Unknown instance: {instance_id}")
    _active_file().write_text(
        json.dumps({"instance_id": instance_id, "updated_at": _now_iso()}, indent=2),
        encoding="utf-8",
    )
    inst = get_instance(instance_id)
    if inst:
        save_instance(inst)


def load_workspace_summary(instance_id: str) -> str:
    path = workspace_summary_path(instance_id)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def save_workspace_summary(instance_id: str, text: str) -> None:
    ensure_instances_root()
    instance_dir(instance_id).mkdir(parents=True, exist_ok=True)
    workspace_summary_path(instance_id).write_text(text, encoding="utf-8")


def append_conversation_archive(instance_id: str, record: dict[str, Any]) -> None:
    if os.getenv("AQUILA_CONVERSATION_ARCHIVE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return
    ensure_instances_root()
    instance_dir(instance_id).mkdir(parents=True, exist_ok=True)
    line = json.dumps({**record, "ts": _now_iso()}, ensure_ascii=False)
    with open(conversation_archive_path(instance_id), "a", encoding="utf-8") as f:
        f.write(line + "\n")
