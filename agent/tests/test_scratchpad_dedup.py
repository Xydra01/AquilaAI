import pytest
from agent.tool_library.agent_tools import _note_similarity

def test_note_similarity():
    # Exactly the same
    assert _note_similarity("hello world", "hello world") == 1.0
    
    # Completely different
    assert _note_similarity("hello world", "foo bar") == 0.0
    
    # Partial overlap
    assert abs(_note_similarity("hello world", "hello there") - 0.3333) < 0.001
    
    # 85% overlap
    text1 = "the quick brown fox jumps over the lazy dog exactly once today"
    text2 = "the quick brown fox jumps over the lazy dog exactly once tomorrow"
    sim = _note_similarity(text1, text2)
    assert sim > 0.8  # Should be very similar
    
    # Empty cases
    assert _note_similarity("", "") == 0.0
    assert _note_similarity("hello", "") == 0.0
    assert _note_similarity("", "hello") == 0.0

    # Case insensitivity
    assert _note_similarity("Hello World", "hello world") == 1.0

    # Punctuation ignored (mostly) by \b\w+\b
    assert _note_similarity("hello, world!", "hello world") == 1.0
