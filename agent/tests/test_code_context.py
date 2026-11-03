"""Tests for Phase 2 code context snapshot and auto-context."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import code_context
from tool_library import code_canvas_tools


@pytest.fixture
def code_project(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    code_canvas_tools.init_code_project("ctxtest", "", "python")
    root = tmp_path / "Agent-Code" / "ctxtest"
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored_dir/\n", encoding="utf-8")
    (root / "ignored_dir").mkdir()
    (root / "ignored_dir" / "secret.py").write_text("x = 1\n", encoding="utf-8")
    yield root


def test_build_project_snapshot_respects_max_chars(code_project):
    snap = code_context.build_project_snapshot(code_project, max_chars=200)
    assert len(snap) <= 220
    assert "main.py" in snap or "Directory tree" in snap


def test_build_project_snapshot_lists_key_files(code_project):
    snap = code_context.build_project_snapshot(code_project, max_chars=8000)
    assert "README.md" in snap or "main.py" in snap


def test_build_project_context_block_includes_snapshot(code_project):
    block, meta = code_context.build_project_context_block()
    assert "CODE_PROJECT_ROOT" in block
    assert meta.get("snapshot_chars", 0) > 0
    assert "snapshot_wall_ms" in meta


def test_parse_grep_hits():
    out = "[OK] 2 match(es) for 'foo'\nbar.py:10: def foo():\nbaz.py:3: foo = 1"
    hits = code_context.parse_grep_hits(out)
    assert hits == [("bar.py", 10), ("baz.py", 3)]


def test_maybe_auto_context_after_grep_disabled(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_AUTO_CONTEXT", "0")
    out = "bar.py:1: match"
    assert code_context.maybe_auto_context_after_grep("grep", out) is None


def test_maybe_auto_context_after_grep_too_many_files(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_AUTO_CONTEXT", "1")
    lines = "\n".join(f"f{i}.py:{i}: x" for i in range(5))
    assert code_context.maybe_auto_context_after_grep("grep", lines) is None


def test_maybe_auto_context_after_grep_injects_snippet(code_project, monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_AUTO_CONTEXT", "1")
    (code_project / "hit.py").write_text("line1\ndef target():\n    return 1\n", encoding="utf-8")
    out = "[OK] 1 match(es)\nhit.py:2: def target():"
    block = code_context.maybe_auto_context_after_grep("grep", out)
    assert block is not None
    assert "Auto-context" in block
    assert "target" in block
