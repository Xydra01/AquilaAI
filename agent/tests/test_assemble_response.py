import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import JSON_REASONING_PREFILL, assemble_agent_response, parse_agent_response


def test_assemble_continuation_only():
    prefill = f"```json\n{JSON_REASONING_PREFILL}"
    raw = 'Map the repo.", "tools": [{"name": "read_code_outline", "arguments": {}}]}'
    text = assemble_agent_response(prefill, raw)
    parsed = parse_agent_response(text, quiet=True)
    assert parsed.get("tools")
    assert parsed["tools"][0]["name"] == "read_code_outline"


def test_assemble_full_json_object_not_doubled():
    prefill = f"```json\n{JSON_REASONING_PREFILL}"
    raw = '{"reasoning": "ok", "tools": []}'
    text = assemble_agent_response(prefill, raw)
    assert text == raw
    parsed = parse_agent_response(text, quiet=True)
    assert parsed.get("reasoning") == "ok"
    assert parsed.get("tools") == []


def test_assemble_markdown_wrapped_full_json():
    prefill = f"```json\n{JSON_REASONING_PREFILL}"
    raw = '```json\n{"reasoning": "wrapped", "tools": []}\n```'
    text = assemble_agent_response(prefill, raw)
    parsed = parse_agent_response(text, quiet=True)
    assert parsed.get("reasoning") == "wrapped"
