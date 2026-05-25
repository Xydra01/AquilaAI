"""Scratchpad chunking for oversized save_research_note payloads."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_library.agent_tools import (
    MAX_SCRATCHPAD_NOTE_BYTES,
    _utf8_byte_chunks,
    save_research_note,
)


def test_utf8_byte_chunks_respects_limit():
    text = "a" * 20_000
    chunks = _utf8_byte_chunks(text, 8192)
    assert len(chunks) >= 3
    assert "".join(chunks) == text
    for chunk in chunks:
        assert len(chunk.encode("utf-8")) <= 8192


def test_utf8_byte_chunks_unicode_boundaries():
    text = "é" * 10_000  # multi-byte char
    chunks = _utf8_byte_chunks(text, 4000)
    assert "".join(chunks) == text


def test_save_research_note_multiple_rows_sqlite(tmp_path, monkeypatch):
    """Integration: memory returns all chunks via get_scratchpad_notes."""
    from context_budget import set_runtime_context
    from memory import DualMemorySystem

    mem = DualMemorySystem(storage_dir=tmp_path, instance_id="test")
    monkeypatch.setattr(
        "tool_library.agent_tools.get_active_memory",
        lambda: mem,
    )
    set_runtime_context("aquila", 8192)

    payload = "z" * (MAX_SCRATCHPAD_NOTE_BYTES + 2000)
    result = save_research_note("task_chunk", payload)
    assert "scratchpad chunks" in result.lower()

    import sqlite3

    key = mem._scratchpad_key("task_chunk")
    with sqlite3.connect(mem.db_path) as conn:
        rows = conn.execute(
            "SELECT note FROM scratchpad WHERE task_name = ? ORDER BY timestamp ASC",
            (key,),
        ).fetchall()
    assert len(rows) >= 2
    parts = []
    for (note,) in rows:
        if note.startswith("[scratchpad chunk") and "]\n" in note:
            parts.append(note.split("]\n", 1)[-1])
        else:
            parts.append(note)
    assert "".join(parts) == payload
