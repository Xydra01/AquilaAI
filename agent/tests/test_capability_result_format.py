"""Capability result text shown to the LLM after a cap run."""
from agent.capabilities.base import CapabilityResult, format_capability_result_for_llm


def test_format_includes_tool_result_payload():
    result = CapabilityResult.success(
        "Recon (2 part(s)).",
        tool_result="TREE\n├── counter.py\nOUTLINE\n- Counter",
    )
    text = format_capability_result_for_llm(result)
    assert "Recon (2 part(s))." in text
    assert "TREE" in text
    assert "counter.py" in text
    assert "data keys: tool_result" not in text


def test_format_skips_duplicate_payload_when_same_as_summary():
    result = CapabilityResult.success("Created file.", tool_result="Created file.")
    text = format_capability_result_for_llm(result)
    assert text.count("Created file.") == 1


def test_format_truncates_huge_payload():
    huge = "x" * 20_000
    result = CapabilityResult.success("ok", tool_result=huge)
    text = format_capability_result_for_llm(result, payload_cap=1000)
    assert "truncated" in text
    assert len(text) < 5_000


def test_format_includes_scalar_data_fields():
    result = CapabilityResult.success("Tests done.", tests_green=True, tool_result="3 passed")
    text = format_capability_result_for_llm(result)
    assert "3 passed" in text
    assert "tests_green=True" in text
