"""Learn index retrieval caps and formatting."""
from learn_index import format_retrieval_block


def test_format_retrieval_caps_total_chars():
    chunks = [
        {"source": "a.md", "text": "x" * 5000},
        {"source": "b.md", "text": "y" * 5000},
        {"source": "c.md", "text": "z" * 5000},
    ]
    block = format_retrieval_block(chunks, max_chars=6000)
    assert len(block) < 7000
    assert "truncated" in block or "capped" in block
