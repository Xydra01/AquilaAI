"""Offline replay: verify coach hints would apply to recorded failure patterns."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopCoach
from agent.research import UrlVisitRegistry


def test_coach_enhances_duplicate_url_block():
    coach = LoopCoach(mode="character_build", step_kind="search", persona_research_lore=True)
    coach.record_web_search_result(
        "Results:\n1. Wiki\nURL: https://wiki.example/a\n"
        "2. Reddit\nURL: https://reddit.com/r/ffxiv/comments/abc\n"
    )
    reg = UrlVisitRegistry()
    reg.register_visit(
        "https://wiki.example/a",
        via="read_webpage",
        quality="truncated",
        body="nav chrome",
    )
    block = reg.check_read_webpage("https://wiki.example/a")
    assert block
    enhanced = coach.enhance_url_block(block, "https://wiki.example/a", reg)
    assert "COACH" in enhanced
    assert "reddit.com" in enhanced.lower() or "unused URL" in enhanced


def test_coach_duplicate_tool_block_character_build():
    coach = LoopCoach(mode="character_build", step_kind="search")
    msg = coach.enhance_duplicate_tool_block(
        "❌ OS BLOCK: Same tool call repeated three times."
    )
    assert "cap.persona.gather_lore@v1" in msg
    assert "mark_objective_complete" in msg


def test_coach_duplicate_tool_block_research():
    coach = LoopCoach(mode="research", step_kind="search")
    msg = coach.enhance_duplicate_tool_block(
        "❌ OS BLOCK: Same tool call repeated three times."
    )
    assert "cap.research.synthesize_notes@v1" in msg
    assert "cap.research.finalize_deliverable@v1" in msg
    assert "finish_task" not in msg


def test_coach_url_block_character_read_uses_ingest_capability():
    coach = LoopCoach(mode="character_build", step_kind="read", persona_research_lore=True)
    reg = UrlVisitRegistry()
    block = "❌ OS BLOCK: URL already visited."
    enhanced = coach.enhance_url_block(block, "https://example.com", reg)
    assert "cap.persona.ingest_sources@v1" in enhanced
    assert "save_research_note" not in enhanced


def test_emet_log_duplicate_read_pattern():
    repo = Path(__file__).resolve().parents[2]
    emet = repo / "Agent-Logs" / "persona_build_emet-selch_20260526_230643.jsonl"
    if not emet.is_file():
        pytest.skip("Emet-Selch reference log not in workspace")
    fandom_attempts = 0
    with emet.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("tool_name") != "read_webpage":
                continue
            url = (rec.get("arguments") or {}).get("url", "")
            preview = str(rec.get("result_preview") or rec.get("body_preview") or "")
            if "fandom.com" in url or "already fetched" in preview.lower():
                fandom_attempts += 1
    assert fandom_attempts >= 1
    coach = LoopCoach(mode="character_build", step_kind="search", persona_research_lore=True)
    hint = coach.enhance_duplicate_tool_block("❌ OS BLOCK: Same tool call repeated three times.")
    assert "cap.persona.gather_lore@v1" in hint or "mark_objective_complete" in hint
