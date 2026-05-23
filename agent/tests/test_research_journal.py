import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research_journal import (
    format_journal_context,
    journal_path,
    load_journal,
    save_journal,
)


def test_format_journal_context_empty():
    assert format_journal_context("") == ""
    assert format_journal_context("   ") == ""


def test_format_journal_context_wraps():
    out = format_journal_context("My hypothesis")
    assert "HUMAN RESEARCH NOTES" in out
    assert "My hypothesis" in out


def test_save_load_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    save_journal("inst_a", "Note line 1")
    assert load_journal("inst_a") == "Note line 1"
    p = journal_path("inst_a")
    assert p.exists()
