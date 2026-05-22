"""URL visit registry blocking."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from url_visit_registry import UrlVisitRegistry


def test_blocks_repeat_read_webpage_same_step():
    reg = UrlVisitRegistry()
    reg.set_step_index(0)
    reg.register_visit(
        "https://example.com/page",
        via="read_webpage",
        quality="full",
        body="content",
    )
    msg = reg.check_read_webpage("https://example.com/page")
    assert msg is not None
    assert "OS BLOCK" in msg


def test_blocks_paywall_revisit():
    reg = UrlVisitRegistry()
    reg.register_visit(
        "https://link.springer.com/chapter/1",
        via="auto_scrape",
        quality="paywall",
        body="paywall note",
    )
    msg = reg.check_read_webpage("https://link.springer.com/chapter/1")
    assert msg is not None
    assert "paywall" in msg.lower()


def test_duplicate_tool_block_third_time():
    reg = UrlVisitRegistry()
    sig = reg.tool_signature("web_search", {"query": "plankton"})
    sigs = [sig, sig, sig]
    assert reg.duplicate_tool_block(sigs) is not None
