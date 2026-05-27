"""Qwen think-block stripping for conversational stream."""
from main import _ThinkStreamFilter


def test_strips_think_block_before_answer():
    f = _ThinkStreamFilter()
    assert f.feed("Hello") == "Hello"
    assert f.feed(" world") == " world"


def test_holds_think_until_close():
    f = _ThinkStreamFilter()
    open_tag = "<" + "think" + ">"
    close_tag = "<" + "/" + "think" + ">"
    assert f.feed("") == ""
    assert f.feed(open_tag + "hidden reasoning") == ""
    mid = f.feed(close_tag + "Answer after think.")
    assert "hidden" not in mid
    assert "Answer" in mid
