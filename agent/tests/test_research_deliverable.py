"""Tests for research deliverable recovery."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research_deliverable import pick_best_deliverable_body, recover_research_body
from main import save_task_deliverable
from web_enrichment import SourceRegistry


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


def test_save_task_deliverable_recovers_from_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class FakeMem:
        def get_scratchpad_notes(self, task_name, instance_id=None):
            if task_name == "agentic_architectures":
                return """--- Note 1 ---
## EXECUTIVE SUMMARY

Recovered body from wrong task name alias with sufficient length for validation.
"""
            return "No research notes found."

    reg = SourceRegistry()
    reg.register("https://example.com", via="read_webpage")
    path = save_task_deliverable(
        "my_task",
        "research",
        "",
        reg,
        memory=FakeMem(),
    )
    assert path is not None
    text = open(path, encoding="utf-8").read()
    assert "EXECUTIVE SUMMARY" in text
    assert "## References" in text


def test_save_task_deliverable_skips_bibliography_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class EmptyMem:
        def get_scratchpad_notes(self, task_name, instance_id=None):
            return "No research notes found."

    reg = SourceRegistry()
    reg.register("https://example.com", via="read_webpage")
    path = save_task_deliverable("empty_task", "research", "", reg, memory=EmptyMem())
    assert path is None
