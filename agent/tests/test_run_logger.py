"""Run logger truncation and JSONL."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_logger import RunLogger, _truncate


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
