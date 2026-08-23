import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import load_attachments_for_mcp, parse_file_paths_arg


def test_parse_file_paths_json_and_csv():
    assert parse_file_paths_arg('["a.py", "b.md"]') == ["a.py", "b.md"]
    assert parse_file_paths_arg("a.py, b.md") == ["a.py", "b.md"]


def test_load_attachments_includes_local_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    f = tmp_path / "notes.txt"
    f.write_text("generation lock details", encoding="utf-8")
    chunks, images, ctx = load_attachments_for_mcp(
        str(f),
        prefer_local=True,
        context="Summarize lock.",
        mode="research",
    )
    assert chunks
    assert "generation lock" in chunks[0]
    assert images == []
    assert "LOCAL RESEARCH" in ctx
    assert "cap.research.ingest_offline@v1" in ctx
    assert "notes.txt" in ctx


def test_load_attachments_tool_hint_for_non_research_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    f = tmp_path / "notes.txt"
    f.write_text("data", encoding="utf-8")
    _, _, ctx = load_attachments_for_mcp(str(f), prefer_local=True, mode="code")
    assert "web_search" in ctx
    assert "cap.research" not in ctx
