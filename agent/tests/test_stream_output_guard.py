"""Tests for streamed chat degeneration detection and trimming."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.parser import (
    has_line_repetition_loop,
    has_phrase_repetition_loop,
    should_stop_stream,
    trim_degenerate_tail,
)


@pytest.fixture(autouse=True)
def _force_guard_on(monkeypatch):
    """Pin the guard enabled so detection tests ignore any ambient .env switch."""
    monkeypatch.setenv("AQUILA_STREAM_GUARD", "1")


def _pi_revision_loop() -> str:
    lines = ["Title now captures essence of project"] * 20
    lines += ["Used online resources to help polish text"] * 15
    return "Good intro paragraph.\n\n" + "\n".join(lines)


def test_has_line_repetition_loop_detects_runaway():
    assert has_line_repetition_loop(_pi_revision_loop())


def test_phrase_repetition_detects_early():
    line = "Title now captures essence of project\n"
    text = "Intro.\n\n" + line * 5
    assert len(text) < 400
    assert has_phrase_repetition_loop(text)
    assert should_stop_stream(text)


def test_should_stop_stream_after_enough_chars():
    short = "Title now captures essence\n" * 2
    assert not should_stop_stream(short)
    assert should_stop_stream(_pi_revision_loop())


def test_trim_degenerate_tail_keeps_intro():
    raw = _pi_revision_loop()
    trimmed = trim_degenerate_tail(raw)
    assert "Good intro paragraph" in trimmed
    assert trimmed.count("Title now captures essence") < raw.count(
        "Title now captures essence"
    )


def test_trim_leaves_clean_text_unchanged():
    clean = "Here is a concise answer about plankton classification."
    assert trim_degenerate_tail(clean) == clean
