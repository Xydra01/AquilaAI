"""Step-entry and budget nudge strings for capability-act modes."""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.loop_engine import LoopEngine
from agent.storage import DualMemorySystem


def _engine(mode: str, *, offline_research: bool = False, tmp_path=None) -> LoopEngine:
    mem_dir = str(tmp_path / "mem") if tmp_path is not None else "/tmp/cap-hint-mem"
    mem = DualMemorySystem(storage_dir=mem_dir, instance_id="default")
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Test.",
        mode=mode,
        mode_label=mode,
        plan_dir="Agent-Plans",
        memory=mem,
        offline_research=offline_research,
    )
    return engine


def _hint_os_line(engine: LoopEngine, step_kind: str) -> str:
    msgs = engine._build_step_entry_messages("task_hint_test", step_kind)
    assert msgs
    for line in msgs[0]["content"].splitlines():
        if line.startswith("OS HINT:"):
            return line
    raise AssertionError("OS HINT line missing from step entry message")


def test_character_step_entry_hints_use_capability_ids(tmp_path):
    engine = _engine("character_build", tmp_path=tmp_path)
    search = _hint_os_line(engine, "search")
    read = _hint_os_line(engine, "read")
    finalize = _hint_os_line(engine, "finalize")
    assert "cap.persona.gather_lore@v1" in search
    assert "cap.persona.ingest_sources@v1" in read
    assert "cap.persona.finalize@v1" in finalize
    assert "web_search" not in search
    assert "save_research_note" not in read
    assert "write_persona_file" not in search


def test_research_step_entry_hints_use_capability_ids(tmp_path):
    engine = _engine("research", tmp_path=tmp_path)
    search = _hint_os_line(engine, "search")
    synth = _hint_os_line(engine, "synthesize")
    finalize = _hint_os_line(engine, "finalize")
    assert "cap.research.gather_web_sources@v1" in search
    assert "cap.research.synthesize_notes@v1" in synth
    assert "cap.research.finalize_deliverable@v1" in finalize
    assert "web_search" not in search
    assert "finish_task" not in finalize


def test_research_offline_step_entry_hints(tmp_path):
    engine = _engine("research", offline_research=True, tmp_path=tmp_path)
    search = _hint_os_line(engine, "search")
    work = _hint_os_line(engine, "work")
    assert "cap.research.ingest_offline@v1" in search
    assert "cap.research.ingest_offline@v1" in work
    assert "web_search" not in search


def test_capability_budget_and_stall_nudges():
    engine = _engine("research")
    assert "cap.research.finalize_deliverable@v1" in engine._capability_budget_override_msg(
        is_final_step=True
    )
    assert "finish_task" not in engine._capability_step_budget_final_override()
    assert "cap.research.finalize_deliverable@v1" in engine._capability_final_stall_nudge()

    char = _engine("character_build")
    assert "cap.persona.finalize@v1" in char._capability_budget_override_msg(is_final_step=True)

    learn = _engine("learn_syllabus_build")
    assert "cap.learn.finalize_course@v1" in learn._capability_final_stall_nudge()

    task = _engine("task")
    assert "finish_task" in task._capability_budget_override_msg(is_final_step=True)
