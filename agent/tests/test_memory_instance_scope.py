import pytest

from memory import DualMemorySystem


@pytest.fixture
def mem_a(tmp_path):
    return DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="alpha")


@pytest.fixture
def mem_b(tmp_path):
    return DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="beta")


def test_scratchpad_namespaced(mem_a, mem_b):
    mem_a.save_scratchpad_note("task1", "note A")
    mem_b.save_scratchpad_note("task1", "note B")
    assert "note A" in mem_a.get_scratchpad_notes("task1")
    assert "note B" in mem_b.get_scratchpad_notes("task1")
    assert "note B" not in mem_a.get_scratchpad_notes("task1")


def test_workspace_summary_row(mem_a):
    mem_a.save_workspace_summary_row("job", "summary text")
    assert mem_a.get_workspace_summary_row("job") == "summary text"
