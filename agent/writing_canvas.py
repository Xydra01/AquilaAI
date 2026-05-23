"""Sync flat markdown canvas text with active_draft_state.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

from workspace_paths import agent_data_path


def draft_path() -> Path:
    return agent_data_path("Agent-Drafts", "active_draft_state.json")


def list_writing_documents() -> list[Path]:
    drafts = agent_data_path("Agent-Drafts")
    if not drafts.exists():
        return []
    out = []
    for p in sorted(drafts.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == "active_draft_state.json":
            continue
        out.append(p)
    return out


def load_markdown_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def markdown_from_draft(state: dict) -> str:
    title = state.get("title", "Untitled")
    lines = [f"# {title}", ""]
    if state.get("synopsis"):
        lines.append(state["synopsis"])
        lines.append("")
    for sec in state.get("sections", []):
        header = sec.get("header", "Section")
        lines.append(f"## {header}")
        lines.append(sec.get("content", ""))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_markdown_to_draft(text: str, *, title: str = "Canvas Document") -> dict:
    """Split markdown into title + sections by ## headers."""
    lines = text.splitlines()
    doc_title = title
    synopsis_parts: list[str] = []
    sections: list[dict] = []
    current_header = None
    current_lines: list[str] = []

    def flush_section() -> None:
        nonlocal current_header, current_lines
        if current_header is not None:
            sections.append(
                {"header": current_header, "content": "\n".join(current_lines).strip()}
            )
        current_header = None
        current_lines = []

    i = 0
    if lines and lines[0].startswith("# "):
        doc_title = lines[0][2:].strip()
        i = 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            flush_section()
            current_header = line[3:].strip()
            i += 1
            continue
        if current_header is None and not sections:
            synopsis_parts.append(line)
        else:
            current_lines.append(line)
        i += 1
    flush_section()
    synopsis = "\n".join(synopsis_parts).strip()
    if not sections and synopsis:
        sections = [{"header": "Body", "content": synopsis}]
        synopsis = ""
    if not sections:
        sections = [{"header": "Body", "content": text.strip()}]
    return {"title": doc_title, "synopsis": synopsis, "sections": sections}


def sync_canvas_to_draft(markdown_text: str) -> str:
    """Write canvas markdown into active_draft_state.json; create if missing."""
    path = draft_path()
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            title = state.get("title", "Canvas Document")
        except Exception:
            state = {}
            title = "Canvas Document"
    else:
        state = {}
        title = "Canvas Document"
    parsed = parse_markdown_to_draft(markdown_text, title=title)
    state.update(parsed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return f"Draft synced ({len(parsed.get('sections', []))} sections)."


def load_active_draft_markdown() -> str | None:
    path = draft_path()
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return markdown_from_draft(state)
    except Exception:
        return None


def has_active_draft() -> bool:
    return draft_path().exists()
