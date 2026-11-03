"""Capability repeat guard — research LoopEngine path (code uses code_agent)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopEngine
from agent.core.loop_coach import LoopCoach
from agent.storage import DualMemorySystem


def _engine(tmp_path):
    mem = DualMemorySystem(storage_dir=str(tmp_path / "mem"), instance_id="default")
    return LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Research mode.",
        mode="research",
        mode_label="Research",
        plan_dir="Agent-Tasks",
        memory=mem,
        base_tools={},
    )


def test_capability_repeat_pre_execute_block_on_third_identical_call(tmp_path):
    engine = _engine(tmp_path)
    engine._schema_tool_names = frozenset({"cap.research.gather_web_sources@v1"})
    coach = LoopCoach(mode="research", capability_research=True)
    call = {
        "id": "cap.research.gather_web_sources@v1",
        "arguments": {"query": "same"},
    }
    sig = LoopEngine._capability_call_signature(call)
    recent = [sig, sig]
    block = engine._capability_repeat_pre_execute_block(
        [call],
        recent,
        loop_coach=coach,
        is_final_step=False,
    )
    assert block is not None
    assert "repeated the same output 3 times" in block


def test_capability_repeat_not_blocked_on_second_call(tmp_path):
    engine = _engine(tmp_path)
    engine._schema_tool_names = frozenset({"cap.research.gather_web_sources@v1"})
    coach = LoopCoach(mode="research", capability_research=True)
    call = {
        "id": "cap.research.gather_web_sources@v1",
        "arguments": {"query": "same"},
    }
    sig = LoopEngine._capability_call_signature(call)
    block = engine._capability_repeat_pre_execute_block(
        [call],
        [sig],
        loop_coach=coach,
        is_final_step=False,
    )
    assert block is None


def test_create_file_retry_hint_escalates():
    hint = LoopCoach.create_file_retry_hint(
        "tests/__init__.py",
        3,
        goal="write tests/test_habit.py first",
    )
    assert "test_habit" in hint.lower()
    assert "attempt 3" in hint.lower()
