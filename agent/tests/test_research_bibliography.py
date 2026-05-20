"""Tests for research bibliography append on deliverables."""
import os

import pytest

from main import save_task_deliverable
from web_enrichment import SourceRegistry, append_bibliography_to_report


def test_append_bibliography_to_report_research():
    reg = SourceRegistry()
    reg.register("https://example.com", title="Example", via="auto_scrape")
    text = append_bibliography_to_report("# Findings\n\nBody.", reg, mode="research")
    assert text.startswith("# Findings")
    assert "## References" in text
    assert "example.com" in text


def test_append_strips_model_references_first():
    reg = SourceRegistry()
    reg.register("https://new.org", via="read_webpage")
    body = "# Report\n\n## References\n\n1. [old](https://old.com)"
    text = append_bibliography_to_report(body, reg, mode="research")
    assert "old.com" not in text
    assert "new.org" in text


def test_non_research_mode_no_bibliography():
    reg = SourceRegistry()
    reg.register("https://example.com", via="auto_scrape")
    text = append_bibliography_to_report("# Task output", reg, mode="task")
    assert "## References" not in text


def test_save_task_deliverable_writes_bibliography(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reg = SourceRegistry()
    reg.register("https://source.edu", title="Source", via="auto_scrape")
    path = save_task_deliverable("my_task", "research", "# Report\n\nDone.", reg)
    assert path is not None
    content = open(path, encoding="utf-8").read()
    assert "## References" in content
    assert "source.edu" in content
