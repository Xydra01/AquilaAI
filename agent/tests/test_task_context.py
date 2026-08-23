"""OS-bound scratchpad task id (model cannot pick wrong task_name)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import ToolExecutor, validate_tool_arguments
from agent.parser import _arguments_json_properties
from agent.core import (
    active_task,
    get_active_task_id,
    inject_scratchpad_task_id,
    omit_task_name_from_schema,
)
from tool_library.agent_tools import save_research_note


def test_omit_task_name_from_schema():
    assert omit_task_name_from_schema("save_research_note", "task_name")
    assert not omit_task_name_from_schema("save_research_note", "gathered_data")
    assert not omit_task_name_from_schema("web_search", "query")


def test_schema_properties_exclude_task_name():
    from tool_library.agent_tools import save_research_note as srn

    props, required = _arguments_json_properties("save_research_note", srn)
    assert "task_name" not in props
    assert "gathered_data" in required


def test_inject_ignores_wrong_model_task_name():
    with active_task("research_correct"):
        args = inject_scratchpad_task_id(
            "save_research_note",
            {"gathered_data": "fact", "task_name": "wrong_slug"},
        )
        assert args["task_name"] == "research_correct"


def test_validate_ignores_bogus_argument():
    from agent.parser import validate_tool_arguments_pydantic

    ok, err, normalized = validate_tool_arguments_pydantic(
        [
            {
                "name": "save_research_note",
                "arguments": {
                    "bogus_arg": "wrong",
                    "gathered_data": "x",
                },
            }
        ],
    )
    assert ok is True
    assert "bogus_arg" not in normalized[0]["arguments"]
    assert normalized[0]["arguments"]["gathered_data"] == "x"


def test_executor_uses_active_task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from agent.storage import DualMemorySystem

    mem = DualMemorySystem(storage_dir=tmp_path, instance_id="test-inst")
    monkeypatch.setattr(
        "tool_library.agent_tools.get_active_memory",
        lambda: mem,
    )

    with active_task("task_bind"):
        ToolExecutor().execute(
            [
                {
                    "name": "save_research_note",
                    "arguments": {"gathered_data": "bound note"},
                }
            ]
        )
    notes = mem.get_scratchpad_notes("task_bind")
    assert "bound note" in notes
