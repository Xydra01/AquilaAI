"""Tests for research deliverable recovery."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.research import pick_best_deliverable_body, recover_research_body


def test_pick_best_prefers_final_synthesis():
    compiled = """=== SCRATCHPAD NOTES FOR t ===
--- Note 1 ---
Short bullet list.

--- Note 2 ---
FINAL SYNTHESIS DATA:

## EXECUTIVE SUMMARY

Long analysis here with enough content to qualify as a report body for the task.
"""
    body = pick_best_deliverable_body(compiled)
    assert "EXECUTIVE SUMMARY" in body
    assert "Short bullet" not in body


def test_recover_uses_active_task_notes_only(tmp_path):
    from agent.storage import DualMemorySystem
    from agent.core import active_task

    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    mem.save_scratchpad_note("my_task", "Short note.")
    mem.save_scratchpad_note(
        "other_slug",
        "FINAL SYNTHESIS\n\n## EXECUTIVE SUMMARY\n\n" + ("Analysis. " * 80),
    )
    with active_task("my_task"):
        mem.save_scratchpad_note(
            "my_task",
            "FINAL SYNTHESIS\n\n## EXECUTIVE SUMMARY\n\n" + ("Analysis. " * 80),
        )
        body = recover_research_body(mem, "my_task")
    assert "EXECUTIVE SUMMARY" in body


def test_recover_ignores_other_task_scratchpads(tmp_path):
    from agent.storage import DualMemorySystem

    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    mem.save_scratchpad_note(
        "other_slug",
        "FINAL SYNTHESIS\n\n## EXECUTIVE SUMMARY\n\n" + ("Analysis. " * 80),
    )
    body = recover_research_body(mem, "my_task")
    assert body == ""


def test_normalize_report_markdown_literal_escapes():
    from agent.core.main import normalize_report_markdown

    raw = "# Title\\n\\n## Section\\nBody line one.\\n\\nMore text."
    fixed = normalize_report_markdown(raw)
    assert "\\n" not in fixed
    assert "# Title\n\n## Section" in fixed
    assert "Body line one." in fixed


def test_save_task_deliverable_repairs_literal_newlines(tmp_path, monkeypatch):
    from agent.core.main import save_task_deliverable
    from agent.storage import agent_data_path

    monkeypatch.setattr(
        "agent.core.main.agent_data_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    path = save_task_deliverable(
        "mongol_test",
        "research",
        "# Report\\n\\n## Intro\\nParagraph one.",
        sources=None,
    )
    assert path is not None
    text = (tmp_path / "Agent-Research" / "mongol_test.md").read_text(encoding="utf-8")
    assert "\\n" not in text.split("## References")[0]
    assert "## Intro\nParagraph" in text
