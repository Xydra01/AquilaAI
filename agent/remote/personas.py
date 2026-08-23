"""Character persona helpers for the Remote Companion REST endpoints.

Thin wrappers over :mod:`persona_registry` that return JSON-serializable dicts
and build the persona-build prompt/task the same way the desktop GUI does.
"""
from __future__ import annotations

from typing import Any, Optional


def _persona_info(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "display_name": p.display_name,
        "tagline": p.tagline,
        "description": p.description,
        "greeting": p.greeting,
        "build_complete": bool(p.build_complete),
        "created_at": p.created_at,
        "last_chat_at": p.last_chat_at,
    }


def list_personas(instance_id: str) -> list[dict[str, Any]]:
    import persona_registry as pr

    return [_persona_info(p) for p in pr.list_personas(instance_id)]


def get_persona(instance_id: str, persona_id: str) -> Optional[dict[str, Any]]:
    import persona_registry as pr

    p = pr.get_persona(instance_id, persona_id)
    return _persona_info(p) if p else None


def build_prompt(persona, description: str, research_lore: bool) -> str:
    """Mirror the GUI's persona-build prompt (character_page._start_persona_build)."""
    lore_line = (
        "User enabled web research for lore — gather lore on the search step."
        if research_lore
        else "Files/text-only intake — do not use web research."
    )
    build_steps = (
        "search (gather lore) → read (ingest) → synthesize (write initialization.md) → finalize"
        if research_lore
        else "read (ingest) → synthesize (write initialization.md) → finalize"
    )
    return (
        f"Build a roleplay persona.\n"
        f"Display name: {persona.display_name}\n"
        f"User description:\n{description}\n\n"
        f"{lore_line}\n"
        f"Persona id: {persona.id}\n"
        f"Phases: {build_steps}."
    )


def create_persona_for_build(
    instance_id: str, display_name: str, description: str, research_lore: bool
) -> dict[str, Any]:
    """Create a (not-yet-built) persona and return the task wiring for /api/task."""
    import persona_registry as pr
    from agent.storage import agent_data_path

    persona = pr.create_persona(
        instance_id, display_name, description, build_complete=False
    )
    pr.sources_dir(instance_id, persona.id).mkdir(parents=True, exist_ok=True)
    task_name = f"persona_build_{persona.id}"
    stale = agent_data_path("Agent-Tasks", f"{task_name}.json")
    if stale.is_file():
        try:
            stale.unlink()
        except OSError:
            pass
    return {
        "persona": _persona_info(persona),
        "task_name": task_name,
        "mode": "character_build",
        "prompt": build_prompt(persona, description, research_lore),
        "persona_research_lore": bool(research_lore),
    }


def delete_persona(instance_id: str, persona_id: str) -> bool:
    import persona_registry as pr

    return pr.delete_persona(instance_id, persona_id)


def load_history(instance_id: str, persona_id: str) -> list[dict[str, str]]:
    import persona_registry as pr

    return pr.load_chat_history(instance_id, persona_id)


def load_preferences(instance_id: str, persona_id: str) -> str:
    import persona_registry as pr

    return pr.load_user_preferences(instance_id, persona_id)


def save_preferences(instance_id: str, persona_id: str, text: str) -> None:
    import persona_registry as pr

    pr.save_user_preferences(instance_id, persona_id, text)
