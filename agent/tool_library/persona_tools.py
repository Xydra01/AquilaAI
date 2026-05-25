"""Tools for Character AI persona build (initialization document)."""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from persona_registry import (
    Persona,
    get_persona,
    initialization_path,
    persona_json_path,
    save_persona,
)

# Active build context: set by GUI / run_unified_task before loop
_active_build: dict[str, Any] | None = None

INIT_DOC_MIN_CHARS = 800


def set_active_persona_build(instance_id: str, persona_id: str) -> None:
    global _active_build
    _active_build = {
        "instance_id": instance_id,
        "persona_id": persona_id,
        "init_written": False,
    }


def clear_active_persona_build() -> None:
    global _active_build
    _active_build = None


def get_active_persona_build() -> dict[str, Any] | None:
    return _active_build


def _build_root() -> Path | None:
    if not _active_build:
        return None
    from persona_registry import persona_dir

    return persona_dir(_active_build["instance_id"], _active_build["persona_id"])


def _normalize_persona_file_path(file_path: str) -> str:
    """Only allow initialization.md under the active persona dir (no absolute paths)."""
    raw = (file_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("file_path is required (use 'initialization.md').")
    p = Path(raw)
    if p.is_absolute():
        raise ValueError(
            "Do not pass an absolute path. Use file_path='initialization.md' only."
        )
    if ".." in p.parts or len(p.parts) != 1:
        raise ValueError(
            f"file_path must be exactly 'initialization.md' (got {file_path!r}). "
            "Do not include instance id, persona_build_*, or other directories."
        )
    if p.name.lower() != "initialization.md":
        raise ValueError(
            f"Only initialization.md is allowed during persona build (got {file_path!r})."
        )
    return "initialization.md"


def initialization_doc_ready(instance_id: str, persona_id: str) -> bool:
    path = initialization_path(instance_id, persona_id)
    if not path.is_file():
        return False
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").strip()) >= INIT_DOC_MIN_CHARS
    except OSError:
        return False


def write_persona_file(file_path: str, content: str) -> str:
    """Write a file under the active persona build directory (e.g. initialization.md)."""
    root = _build_root()
    if not _active_build:
        return "❌ Error: No active persona build session."
    try:
        rel = _normalize_persona_file_path(file_path)
    except ValueError as e:
        return f"❌ Error: {e}"
    text = (content or "").strip()
    iid = _active_build["instance_id"]
    pid = _active_build["persona_id"]
    canon = initialization_path(iid, pid)

    if rel == "initialization.md":
        if len(text) < INIT_DOC_MIN_CHARS:
            return (
                f"❌ initialization.md is only {len(text)} characters "
                f"(need at least {INIT_DOC_MIN_CHARS}). Add personality, voice, backstory, and scene."
            )
        if _active_build.get("init_written") or initialization_doc_ready(iid, pid):
            _active_build["init_written"] = True
            return (
                "❌ OS BLOCK: initialization.md is already written. "
                "Do NOT call write_persona_file again. "
                "Call finalize_persona(greeting=..., tagline=...) then mark_objective_complete."
            )

    target = canon
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + ("\n" if text and not text.endswith("\n") else ""), encoding="utf-8")
    _active_build["init_written"] = True
    return (
        f"✅ Wrote {len(text)} characters to {canon.as_posix()}. "
        "Do NOT rewrite — call finalize_persona(greeting=..., tagline=...) "
        "then mark_objective_complete."
    )


def finalize_persona(
    greeting: str,
    tagline: str = "",
    display_name: str = "",
) -> str:
    """Complete persona build: save greeting and mark persona ready."""
    if not _active_build:
        return "❌ Error: No active persona build session."
    iid = _active_build["instance_id"]
    pid = _active_build["persona_id"]
    persona = get_persona(iid, pid)
    if not persona:
        return "❌ Error: Persona record not found."
    init_path = initialization_path(iid, pid)
    if not init_path.is_file() or init_path.stat().st_size < INIT_DOC_MIN_CHARS:
        return (
            f"❌ Error: Write initialization.md first (at least {INIT_DOC_MIN_CHARS} characters) "
            "via write_persona_file."
        )
    if display_name.strip():
        persona.display_name = display_name.strip()
    persona.greeting = (greeting or "").strip() or "Hello."
    persona.tagline = (tagline or "").strip()
    persona.build_complete = True
    save_persona(iid, persona)
    clear_active_persona_build()
    return f"✅ Persona '{persona.display_name}' finalized and ready for chat."


PERSONA_TOOLS = {
    "write_persona_file": {
        "func": write_persona_file,
        "description": inspect.getdoc(write_persona_file),
    },
    "finalize_persona": {
        "func": finalize_persona,
        "description": inspect.getdoc(finalize_persona),
    },
}
