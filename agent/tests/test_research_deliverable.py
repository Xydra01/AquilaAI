"""Tests for research deliverable recovery."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research_deliverable import pick_best_deliverable_body, recover_research_body


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


def test_recover_prefers_synthesis_over_short_note(tmp_path):
    from memory import DualMemorySystem

    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    mem.save_scratchpad_note("my_task", "Short note.")
    mem.save_scratchpad_note(
        "other_slug",
        "FINAL SYNTHESIS\n\n## EXECUTIVE SUMMARY\n\n" + ("Analysis. " * 80),
    )
    body = recover_research_body(mem, "my_task")
    assert "EXECUTIVE SUMMARY" in body
