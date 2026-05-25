import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from writing_canvas import (
    markdown_from_draft,
    parse_markdown_to_draft,
    sync_canvas_to_draft,
)


def test_parse_markdown_sections():
    md = "# Title\n\nIntro\n\n## Sec A\n\nBody A\n\n## Sec B\n\nBody B"
    draft = parse_markdown_to_draft(md)
    assert draft["title"] == "Title"
    assert len(draft["sections"]) >= 2


def test_sync_canvas_to_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    drafts = tmp_path / "Agent-Drafts"
    drafts.mkdir()
    msg = sync_canvas_to_draft("# Doc\n\n## One\n\nHello")
    assert "synced" in msg.lower()
    state = json.loads((drafts / "active_draft_state.json").read_text(encoding="utf-8"))
    assert state["title"] == "Doc"
    assert markdown_from_draft(state).startswith("# Doc")
