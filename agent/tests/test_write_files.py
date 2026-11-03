"""Tests for cap.dev.write_files@v1 batch capability."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities.dev.write_files import WriteFilesInput, _run_write_files
from agent.capabilities.base import CapabilityContext
from agent.storage import agent_data_path


@pytest.fixture
def code_canvas_state(tmp_path, monkeypatch):
    code_dir = agent_data_path("Agent-Code")
    code_dir.mkdir(parents=True, exist_ok=True)
    project_root = code_dir / "batch-test"
    state = {"project_id": "batch-test", "root": str(project_root), "files": []}
    (code_dir / "active_code_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    yield state
    if (code_dir / "active_code_state.json").is_file():
        (code_dir / "active_code_state.json").unlink()


def test_write_files_creates_multiple_buffer_files(code_canvas_state):
    ctx = CapabilityContext(
        task_id="batch_test",
        mode="code",
        step_kind="work",
        step_index=0,
    )
    inp = WriteFilesInput(
        files=[
            {"file_path": "a.py", "content": "print('a')\n"},
            {"file_path": "b.py", "content": "print('b')\n"},
            {"file_path": "tests/test_a.py", "content": "def test_a():\n    assert True\n"},
        ]
    )
    result = _run_write_files(ctx, inp)
    assert result.ok
    assert len(result.data.get("files") or []) == 3


def test_timing_breakdown_from_jsonl():
    from agent.core.capability_harness import _timing_breakdown_from_jsonl

    empty = _timing_breakdown_from_jsonl(None)
    assert empty["reflect_calls"] == 0
    assert empty["act_calls"] == 0
