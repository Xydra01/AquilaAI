import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    analyze_jsonl,
    score_jsonl_for_scenario,
    write_scorecard_jsonl,
)


@pytest.fixture
def sample_jsonl(tmp_path):
    path = tmp_path / "run.jsonl"
    events = [
        {"ts": "2026-05-26T23:06:43", "event": "session_start", "task": "t", "mode": "character_build"},
        {"ts": "2026-05-26T23:06:50", "event": "llm_request"},
        {"ts": "2026-05-26T23:10:00", "event": "os_warning", "message": "read_timeout"},
        {
            "ts": "2026-05-26T23:12:15",
            "event": "llm_response",
            "step_index": 0,
            "episode": 2,
            "step_kind": "search",
        },
        {"ts": "2026-05-26T23:12:17", "event": "scrape_budget_exhausted"},
        {
            "ts": "2026-05-26T23:12:25",
            "event": "tool_start",
            "tool_name": "read_webpage",
            "arguments": {"url": "https://example.com/wiki"},
        },
        {
            "ts": "2026-05-26T23:12:36",
            "event": "tool_end",
            "tool_name": "read_webpage",
            "result_preview": "❌ OS BLOCK: already fetched this run",
        },
        {
            "ts": "2026-05-26T23:12:54",
            "event": "tool_start",
            "tool_name": "save_research_note",
            "arguments": {"gathered_data": "fact one. fact two. fact three."},
        },
    ]
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return path


def test_analyze_jsonl_counts(sample_jsonl):
    card = analyze_jsonl(
        sample_jsonl,
        max_episodes_per_step=6,
        max_duplicate_blocks=5,
        max_read_timeouts=2,
    )
    assert card.read_timeouts == 1
    assert card.scrape_budget_exhausted == 1
    assert card.url_blocks == 1
    assert card.max_episode_per_step == 2
    assert card.wall_time_s is not None
    assert card.passed


def test_forced_advance_rubric(tmp_path):
    path = tmp_path / "forced.jsonl"
    events = [
        {"ts": "2026-05-26T23:00:00", "event": "forced_advance", "reason": "iteration_limit"},
        {"ts": "2026-05-26T23:00:01", "event": "palette_mode", "dynamic": True},
    ]
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    card = analyze_jsonl(path, max_forced_advance_count=0)
    assert card.forced_advance_count == 1
    assert not card.passed
    card_ok = analyze_jsonl(path, max_forced_advance_count=1)
    assert card_ok.passed


def test_degenerate_scratchpad_fails(sample_jsonl):
    path = sample_jsonl
    degenerate = "Complex antagonist, " * 40
    with path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "event": "tool_end",
                    "tool_name": "save_research_note",
                    "arguments": {"gathered_data": degenerate},
                }
            )
            + "\n"
        )
    card = analyze_jsonl(path)
    assert card.degenerate_scratchpad
    assert not card.passed


def test_write_scorecard_jsonl(sample_jsonl, tmp_path):
    card = analyze_jsonl(sample_jsonl)
    out = write_scorecard_jsonl(card, tmp_path / "scorecard.jsonl")
    assert out.is_file()
    line = out.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["passed"] == card.passed


def test_analyze_jsonl_throughput_aggregates(tmp_path):
    path = tmp_path / "tps.jsonl"
    events = [
        {"ts": "2026-01-01T12:00:00", "event": "llm_request", "est_tokens": 1000},
        {
            "ts": "2026-01-01T12:00:02",
            "event": "llm_response",
            "duration_ms": 1000,
            "body": "a" * 120,
            "output_tokens_per_s": 30.0,
            "output_tokens_est": 30,
        },
        {
            "ts": "2026-01-01T12:00:04",
            "event": "llm_response",
            "duration_ms": 2000,
            "body": "b" * 80,
            "output_tokens_est": 40,
            "output_tokens_per_s": 20.0,
        },
        {"ts": "2026-01-01T12:00:05", "event": "tool_end", "tool_name": "grep"},
    ]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    card = analyze_jsonl(path)
    assert card.tool_call_count == 1
    assert card.total_prompt_tokens_est == 1000
    assert card.median_output_tokens_per_s == 25.0
    assert card.total_output_tokens_est >= 30


def test_score_emet_log_if_present():
    repo = Path(__file__).resolve().parents[2]
    emet = repo / "Agent-Logs" / "persona_build_emet-selch_20260526_230643.jsonl"
    if not emet.is_file():
        pytest.skip("Emet-Selch reference log not in workspace")
    card = score_jsonl_for_scenario(emet, "persona_build_lore")
    assert card.llm_requests >= 1
    assert card.read_timeouts >= 1


def test_finalize_capability_satisfies_require_finish(tmp_path):
    path = tmp_path / "cap_finalize.jsonl"
    events = [
        {"ts": "2026-01-01T12:00:00", "event": "tool_start", "tool_name": "cap:cap.research.gather_web_sources@v1"},
        {"ts": "2026-01-01T12:00:05", "event": "tool_start", "tool_name": "cap:cap.research.gather_web_sources@v1"},
        {"ts": "2026-01-01T12:00:10", "event": "tool_start", "tool_name": "cap:cap.web.read_pages@v1"},
        {
            "ts": "2026-01-01T12:00:20",
            "event": "tool_end",
            "tool_name": "cap:cap.research.finalize_deliverable@v1",
            "result_preview": "✅ Deliverable saved",
        },
    ]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    card = analyze_jsonl(
        path,
        require_finish=True,
        min_web_search=2,
        min_read_webpage=1,
    )
    assert card.capability_finalize
    assert card.passed
    assert "finalize capability seen" in card.passes
