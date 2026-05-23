"""Per-instance human research journal (markdown) for GUI injection."""
from __future__ import annotations

from pathlib import Path

from workspace_paths import agent_data_path


def journal_path(instance_id: str) -> Path:
    root = agent_data_path("Agent-Research", ".journal")
    root.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in instance_id)
    return root / f"{safe}.md"


def load_journal(instance_id: str) -> str:
    path = journal_path(instance_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def save_journal(instance_id: str, text: str) -> None:
    path = journal_path(instance_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")


def format_journal_context(text: str) -> str:
    if not (text or "").strip():
        return ""
    return (
        "\n\n--- HUMAN RESEARCH NOTES ---\n"
        f"{text.strip()}\n"
        "--- END HUMAN RESEARCH NOTES ---\n"
    )
