"""Tests for schema_policy constrained decoding."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies.schema_policy import (
    TurnSchemaContext,
    compile_turn_schema,
    resolve_schema_spec,
)


def test_resolve_omits_finish_task_when_not_final():
    ctx = TurnSchemaContext(
        mode="research",
        step_kind="search",
        allowed_tools=frozenset({"web_search", "finish_task", "read_webpage"}),
        is_final_step=False,
        allow_finish_task=False,
    )
    spec = resolve_schema_spec(ctx)
    assert "finish_task" not in spec.allowed_tools
    assert "finish_task" in spec.excluded_tools


def test_research_search_step_max_one_tool():
    ctx = TurnSchemaContext(
        mode="research",
        step_kind="search",
        allowed_tools=frozenset({"web_search", "read_webpage"}),
        is_final_step=False,
    )
    spec = resolve_schema_spec(ctx)
    assert spec.max_tools_per_turn == 1


def test_research_search_step_max_one_tool_with_dynamic_loop():
    ctx = TurnSchemaContext(
        mode="research",
        step_kind="search",
        allowed_tools=frozenset({"web_search", "read_webpage"}),
        is_final_step=False,
        dynamic_loop_active=True,
    )
    spec = resolve_schema_spec(ctx)
    assert spec.max_tools_per_turn == 1


def test_compile_schema_has_max_items_for_search():
    registry = {
        "web_search": {"func": lambda query="": None, "description": "search"},
        "read_webpage": {"func": lambda url="": None, "description": "read"},
    }
    ctx = TurnSchemaContext(
        mode="research",
        step_kind="search",
        allowed_tools=frozenset(registry.keys()),
    )
    spec = resolve_schema_spec(ctx)
    schema = compile_turn_schema(spec, registry, mode="research", step_kind="search")
    tools = schema["properties"]["tools"]
    assert tools.get("maxItems") == 1


def test_finish_allowed_on_final_step():
    ctx = TurnSchemaContext(
        mode="research",
        step_kind="finalize",
        allowed_tools=frozenset({"finish_task", "save_research_note"}),
        is_final_step=True,
        allow_finish_task=True,
    )
    spec = resolve_schema_spec(ctx)
    assert "finish_task" in spec.allowed_tools
    assert spec.require_final_report is True
