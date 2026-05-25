"""Persona build ingest step — avoid read_all_research_notes loops on empty scratchpad."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loop_engine import LoopEngine
from tool_catalog import (
    CHARACTER_BUILD_SEARCH_TOOLS,
    CHARACTER_BUILD_SYNTHESIZE_TOOLS,
    MODE_REQUIRED,
    allowed_tools_for_step,
)


def test_character_build_mode_required_excludes_read_all():
    required = MODE_REQUIRED["character_build"]
    assert "save_research_note" in required
    assert "read_all_research_notes" not in required


def test_character_build_read_step_allowed_tools_exclude_read_all():
    all_names = {
        "save_research_note",
        "read_all_research_notes",
        "mark_objective_complete",
        "write_persona_file",
        "finalize_persona",
        "web_search",
    }
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="read",
        routed=set(),
        all_names=all_names,
    )
    assert "save_research_note" in allowed
    assert "read_all_research_notes" not in allowed


def test_character_build_synthesize_step_excludes_summarize_sources():
    all_names = {
        "save_research_note",
        "read_all_research_notes",
        "summarize_sources",
        "write_persona_file",
        "replace_in_file",
        "write_file",
        "mark_objective_complete",
        "finalize_persona",
    }
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="synthesize",
        routed={"replace_in_file", "write_file", "grep_repo"},
        all_names=all_names,
    )
    assert "summarize_sources" not in allowed
    assert "replace_in_file" not in allowed
    assert "write_file" not in allowed
    assert "write_persona_file" in allowed
    assert "save_research_note" not in allowed
    assert allowed <= CHARACTER_BUILD_SYNTHESIZE_TOOLS | {
        "mark_objective_complete",
        "finish_task",
    }


def test_character_build_read_ignores_routed_file_tools():
    all_names = {
        "save_research_note",
        "replace_in_file",
        "write_file",
        "read_all_research_notes",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="read",
        routed={"replace_in_file", "write_file"},
        all_names=all_names,
    )
    assert allowed == {"save_research_note", "mark_objective_complete", "finish_task"}


def test_character_build_search_step_allows_web_when_lore_enabled():
    all_names = {
        "web_search",
        "read_webpage",
        "save_research_note",
        "write_persona_file",
        "mark_objective_complete",
        "finish_task",
    }
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="search",
        routed=set(),
        all_names=all_names,
        persona_research_lore=True,
    )
    assert "web_search" in allowed
    assert "read_webpage" in allowed
    assert allowed <= CHARACTER_BUILD_SEARCH_TOOLS | {"mark_objective_complete", "finish_task"}


def test_character_build_search_step_without_lore_flag_uses_routed_pool():
    all_names = {"web_search", "save_research_note", "mark_objective_complete"}
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="search",
        routed={"web_search"},
        all_names=all_names,
        persona_research_lore=False,
    )
    assert "web_search" in allowed


def test_character_build_synthesize_step_allows_read_all():
    all_names = {
        "save_research_note",
        "read_all_research_notes",
        "write_persona_file",
        "mark_objective_complete",
    }
    allowed = allowed_tools_for_step(
        mode="character_build",
        step_kind="synthesize",
        routed=set(),
        all_names=all_names,
    )
    assert "read_all_research_notes" in allowed


def test_auto_ingest_persona_attachments_saves_chunks(monkeypatch, tmp_path):
    from memory_singleton import aquila_memory

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
    from memory_singleton import aquila_memory

    monkeypatch.setattr(
        aquila_memory,
        "get_scratchpad_notes",
        lambda _t: "existing lore",
    )
    engine = LoopEngine.__new__(LoopEngine)
    engine.memory = aquila_memory
    assert engine._auto_ingest_persona_attachments("t", "desc", ["chunk"]) is None
