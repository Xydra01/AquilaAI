"""Unit tests for Phase 1 code agent filesystem tools."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_library import code_agent_tools, code_canvas_tools


@pytest.fixture
def code_project(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    code_canvas_tools.init_code_project("tooltest", "", "python")
    yield tmp_path / "Agent-Code" / "tooltest"


def test_write_and_read_file(code_project):
    out = code_agent_tools.write_file("hello.py", "print('hi')\n")
    assert "Successfully" in out or "✅" in out
    body = code_agent_tools.read_file("hello.py", 1, 5)
    assert "1|print('hi')" in body
    assert (code_project / "hello.py").is_file()


def test_write_file_oversize_rejected(code_project, monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_MAX_WRITE_CHARS", "50")
    out = code_agent_tools.write_file("big.txt", "x" * 100)
    assert "OS BLOCK" in out
    assert not (code_project / "big.txt").exists()


def test_search_replace_unique_match(code_project):
    code_agent_tools.write_file("edit.py", "alpha\nbeta\ngamma\n")
    ok = code_agent_tools.search_replace("edit.py", "beta", "BETA")
    assert "✅" in ok
    text = (code_project / "edit.py").read_text(encoding="utf-8")
    assert "BETA" in text
    assert text.count("beta") == 0


def test_search_replace_zero_matches(code_project):
    code_agent_tools.write_file("edit.py", "only one line\n")
    out = code_agent_tools.search_replace("edit.py", "missing", "x")
    assert "not found" in out.lower()


def test_search_replace_multiple_matches(code_project):
    code_agent_tools.write_file("dup.py", "foo\nfoo\n")
    out = code_agent_tools.search_replace("dup.py", "foo", "bar")
    assert "2 times" in out


def test_list_dir(code_project):
    code_agent_tools.write_file("pkg/mod.py", "x = 1\n")
    out = code_agent_tools.list_dir(".", max_depth=2)
    assert "mod.py" in out or "pkg" in out


def test_grep_finds_content(code_project):
    code_agent_tools.write_file("findme.py", "HARNESS_MARKER = 42\n")
    out = code_agent_tools.grep("HARNESS_MARKER", ".", "*.py")
    assert "findme.py" in out or "HARNESS_MARKER" in out


def test_grep_output_format(code_project):
    code_agent_tools.write_file("fmt.py", "UNIQUE_FMT_TOKEN = 1\n")
    out = code_agent_tools.grep("UNIQUE_FMT_TOKEN", ".", "*.py")
    assert "[OK]" in out
    for line in out.splitlines():
        if "UNIQUE_FMT_TOKEN" in line and ":" in line:
            parts = line.split(":", 2)
            assert len(parts) >= 3
            assert parts[1].isdigit()
            break
    else:
        pytest.fail("expected path:line: content format in grep output")


def test_find_files_glob(code_project):
    code_agent_tools.write_file("tests/test_one.py", "pass\n")
    code_agent_tools.write_file("tests/test_two.py", "pass\n")
    out = code_agent_tools.find_files("test_*.py", "tests")
    assert "test_one.py" in out
    assert "test_two.py" in out


def test_tools_require_project(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    out = code_agent_tools.read_file("x.py")
    assert "No code project" in out
