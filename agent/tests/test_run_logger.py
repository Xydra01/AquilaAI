"""Run logger truncation and JSONL."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import RunLogger, _truncate
from agent.core.run_logger import thinking_log_fields


def test_truncate_flags():
    text, trunc, n = _truncate("x" * 5000, 100)
    assert trunc is True
    assert n == 5000
    assert len(text) < 5000


def test_jsonl_event_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AQUILA_LOG_JSON", "1")
    log = RunLogger()
    log.set_task("test_task", instance_id="default", mode="research")
    log.event("tool_end", tool_name="web_search", body="y" * 10_000)
    assert log.jsonl_filename and os.path.isfile(log.jsonl_filename)
    with open(log.jsonl_filename, encoding="utf-8") as f:
        lines = f.readlines()
    record = json.loads(lines[-1])
    assert record["event"] == "tool_end"
    assert record.get("truncated") is True
    assert "body_preview" in record


def test_thinking_fields_store_full_body(monkeypatch):
    monkeypatch.setenv("AQUILA_LOG_THINK_JSONL_CAP", "2000")
    body = "plan next step: create counter.py\n" * 40
    fields = thinking_log_fields(body)
    assert fields["thinking_chars"] == len(body)
    assert fields["thinking_preview"] == body[:500]
    assert fields["thinking"].startswith("plan next step")
    assert "thinking_sha8" in fields
    assert len(fields["thinking"]) <= 2000 + 80


def test_log_agent_turn_writes_thinking_block(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AQUILA_LOG_JSON", "1")
    monkeypatch.setenv("AQUILA_LOG_THINK_HUMAN", "1")
    log = RunLogger()
    log.set_task("think_task", instance_id="default", mode="code")
    log.log_agent_turn(
        0,
        2,
        "work",
        1,
        1,
        "reflect",
        "next: create_file",
        thinking_preview="I should create counter.py after tests exist.",
    )
    assert log.log_filename and os.path.isfile(log.log_filename)
    human = open(log.log_filename, encoding="utf-8").read()
    assert "THINKING:" in human
    assert "create counter.py" in human
    with open(log.jsonl_filename, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    llm = [r for r in records if r.get("event") == "llm_response"][-1]
    assert "create counter.py" in (llm.get("thinking") or "")
    assert llm.get("thinking_chars", 0) > 20
