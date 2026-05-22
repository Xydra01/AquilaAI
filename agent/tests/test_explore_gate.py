from loop_engine import LoopEngine


def test_explore_gate_blocks_without_evidence():
    gate = LoopEngine._explore_advance_gate([], "")
    assert gate is not None
    assert "explore" in gate.lower()


def test_explore_gate_passes_with_outline_and_read():
    history = [
        {
            "role": "user",
            "content": "Tool 'read_code_outline' result:\nPROJECT: demo",
        },
        {
            "role": "user",
            "content": "Tool 'read_file_region' result:\nline 1",
        },
    ]
    assert LoopEngine._explore_advance_gate(history, "") is None
