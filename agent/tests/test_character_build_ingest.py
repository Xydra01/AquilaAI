"""Persona build ingest step — avoid read_all_research_notes loops on empty scratchpad."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopEngine
from agent.policies import allowed_tools_for_step


def test_character_build_mode_allows_all_assigned_tools():
    all_names = {
        "save_research_note",
        "read_all_research_notes",
        "write_persona_file",
        "finalize_persona",
        "web_search",
        "read_webpage",
    }
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="any",
        routed=set(),
        all_names=all_names,
    )
    # The new mode-based injection paradigm injects all tools for the mode.
    # We just ensure it isn't arbitrarily truncating them anymore.
    assert "save_research_note" in allowed
    assert "write_persona_file" in allowed


def test_auto_ingest_persona_attachments_saves_chunks(monkeypatch, tmp_path):
    from agent.storage import aquila_memory

    saved: dict[str, object] = {"notes": []}

    def fake_save(task_name, data):
        saved["task"] = task_name
        saved["notes"].append(data)
        return "✅ saved"

    monkeypatch.setattr(
        "tool_library.agent_tools.get_active_memory",
        lambda: aquila_memory,
    )
    monkeypatch.setattr(aquila_memory, "save_scratchpad_note", fake_save)
    monkeypatch.setattr(aquila_memory, "get_scratchpad_notes", lambda _t: "")

    engine = LoopEngine.__new__(LoopEngine)
    engine.memory = aquila_memory
    msg = engine._auto_ingest_persona_attachments(
        "persona_build_x",
        "Horror Sans persona",
        ["chunk one lore", "chunk two lore"],
    )
    assert msg is not None
    assert "Pre-ingested" in msg
    combined = "\n".join(saved["notes"])
    assert "Horror Sans" in combined
    assert "chunk one" in combined


def test_auto_ingest_skips_when_scratchpad_already_has_notes(monkeypatch):
    from agent.storage import aquila_memory

    monkeypatch.setattr(
        aquila_memory,
        "get_scratchpad_notes",
        lambda _t: "existing lore",
    )
    engine = LoopEngine.__new__(LoopEngine)
    engine.memory = aquila_memory
    assert engine._auto_ingest_persona_attachments("t", "desc", ["chunk"]) is None
