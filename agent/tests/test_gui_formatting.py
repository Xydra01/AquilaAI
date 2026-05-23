"""Unit tests for display-only GUI formatting."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui_formatting import format_ledger_html, pretty_json_text


def test_pretty_json_text():
    assert pretty_json_text('{"a":1,"b":[2,3]}') == '{\n  "a": 1,\n  "b": [\n    2,\n    3\n  ]\n}'


def test_format_ledger_html_pretty_prints_agent_json():
    raw = (
        "--- Step 1/4 (search) · LLM turn 1 ---\n"
        '{"reasoning": "hi", "tools": [{"name": "web_search", "arguments": {}}]}\n'
        "\nTool 'web_search' result:\nDone.\n"
    )
    html = format_ledger_html(raw)
    assert "step-header" in html
    assert "json-block" in html
    assert '"reasoning"' in html
    assert "web_search" in html


def test_format_ledger_empty_placeholder():
    assert "Waiting" in format_ledger_html("")
