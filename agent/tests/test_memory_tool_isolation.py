"""Tool routing Chroma collections must be per-instance."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory import DualMemorySystem


@pytest.fixture
def mem_a(tmp_path):
    return DualMemorySystem(
        storage_dir=str(tmp_path / "mem"),
        chroma_path=str(tmp_path / "chroma"),
        instance_id="alpha",
    )


@pytest.fixture
def mem_b(tmp_path):
    return DualMemorySystem(
        storage_dir=str(tmp_path / "mem"),
        chroma_path=str(tmp_path / "chroma"),
        instance_id="beta",
    )


def test_tool_collections_are_per_instance(mem_a, mem_b):
    assert mem_a.tool_collection.name != mem_b.tool_collection.name
    assert "alpha" in mem_a.tool_collection.name
    assert "beta" in mem_b.tool_collection.name


def test_recover_scratchpad_wrong_task_slug(mem_a):
    mem_a.save_scratchpad_note(
        "wrong_topic_slug",
        "## EXECUTIVE SUMMARY\n\n" + ("Detail. " * 120),
    )
    from research_deliverable import recover_research_body

    body = recover_research_body(mem_a, "conductacomprehensive_1779419640")
    assert "EXECUTIVE SUMMARY" in body
