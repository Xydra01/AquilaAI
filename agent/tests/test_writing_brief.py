import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.functions.writing_brief import WritingBrief
from agent.functions.writing_scope import draft_metrics, draft_scope_satisfied
from agent.storage.instance_registry import load_writing_defaults, save_writing_defaults


def test_writing_brief_scope_presets():
    quick = WritingBrief.from_scope_preset("quick_edit")
    assert quick.advance_when == "single_draft"
    doc = WritingBrief.from_scope_preset("standard")
    assert doc.advance_when == "scope_met"
    assert doc.target_sections == 4


def test_draft_scope_satisfied_single_draft():
    brief = WritingBrief.from_scope_preset("quick_edit")
    assert draft_scope_satisfied(brief, {"sections": []}, draft_sections_calls=1)
    assert not draft_scope_satisfied(brief, {"sections": []}, draft_sections_calls=0)


def test_draft_scope_satisfied_sections():
    brief = WritingBrief.from_scope_preset("standard")
    state = {"sections": [{"header": "A", "content": "one"}, {"header": "B", "content": "two"}]}
    assert not draft_scope_satisfied(brief, state, draft_sections_calls=2)
    state["sections"].extend([
        {"header": "C", "content": "three"},
        {"header": "D", "content": "four"},
    ])
    assert draft_scope_satisfied(brief, state, draft_sections_calls=4)


def test_draft_metrics_word_count():
    state = {
        "sections": [
            {"header": "Intro", "content": "one two three four"},
        ]
    }
    metrics = draft_metrics(state)
    assert metrics["sections"] == 1
    assert metrics["words"] == 4


def test_writing_defaults_persistence(tmp_path, monkeypatch):
    from agent.storage import instance_registry

    monkeypatch.setattr(instance_registry, "_instances_root", lambda: tmp_path)
    save_writing_defaults("default", {"scope": "short_form", "tone": "formal", "target_value": 300})
    loaded = load_writing_defaults("default")
    assert loaded["scope"] == "short_form"
    assert loaded["tone"] == "formal"
