"""Unit tests for Pydantic structured output builder and parser."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    build_strict_schema,
    get_executable_tools,
    normalize_tool_calls_list,
    parse_agent_response,
    validate_tool_arguments,
    validate_tool_calls,
)
from model_output_profile import format_attempts_for_profile, resolve_model_output_profile
from structured_parse import heal_json_text, parse_structured_turn, try_parse_json
from structured_schema import (
    TaskPlanModel,
    build_arguments_model,
    get_reflect_schema,
    get_task_plan_schema,
    shrink_schema_for_retry,
)


def test_schema_tool_items_use_name_enum():
    schema = build_strict_schema(get_executable_tools())
    items = schema["properties"]["tools"]["items"]
    assert "enum" in items["properties"]["name"]
    assert "write_file" in items["properties"]["name"]["enum"]


def test_arguments_model_uses_int_for_web_search():
    tools = get_executable_tools()
    args_model = build_arguments_model("web_search", tools["web_search"]["func"])
    schema = args_model.model_json_schema()
    props = schema.get("properties", {})
    assert props.get("max_results", {}).get("type") == "integer"


def test_parse_agent_action_strict_no_heal():
    tools = get_executable_tools()
    subset = {k: tools[k] for k in ("list_directory",) if k in tools}
    schema_names = frozenset(subset.keys())
    payload = {
        "reasoning": "List root",
        "tools": [{"name": "list_directory", "arguments": {"path": "."}}],
    }
    text = json.dumps(payload)
    parsed = parse_agent_response(
        text,
        quiet=True,
        tool_names=schema_names,
        format_mode="strict_schema",
        registry=subset,
    )
    assert parsed.get("tools")
    assert parsed["tools"][0]["name"] == "list_directory"


def test_parse_agent_action_markdown_fence():
    payload = {
        "reasoning": "ok",
        "tools": [{"name": "list_directory", "arguments": {"path": "agent"}}],
    }
    text = "```json\n" + json.dumps(payload) + "\n```"
    tools = get_executable_tools()
    subset = {k: tools[k] for k in ("list_directory",) if k in tools}
    parsed = parse_agent_response(
        text,
        quiet=True,
        tool_names=frozenset(subset.keys()),
        format_mode="strict_schema",
        registry=subset,
    )
    assert parsed["tools"][0]["arguments"]["path"] == "agent"


def test_healer_only_when_plain_mode():
    broken = '{"reasoning": "x", "tools": [{"name": "list_directory", "arguments": {"path": "."}'
    from structured_schema import get_agent_action_model

    tools = get_executable_tools()
    names = frozenset(["list_directory"])
    model = get_agent_action_model(names, tools)
    inst, err, meta = parse_structured_turn(
        broken, model, format_mode="strict_schema", allow_heal=False
    )
    assert inst is None
    assert meta.get("error_kind") == "json_decode"

    inst2, _, meta2 = parse_structured_turn(
        broken, model, format_mode="plain", allow_heal=True
    )
    assert inst2 is not None or meta2.get("healed") or try_parse_json(heal_json_text(broken))


def test_task_plan_model_round_trip():
    plan = TaskPlanModel(
        status="in_progress",
        current_step_index=0,
        steps=[
            {
                "status": "pending",
                "description": "Search",
                "step_kind": "search",
                "max_iterations": 4,
            }
        ],
    )
    data = plan.model_dump(mode="python")
    again = TaskPlanModel.model_validate(data)
    assert len(again.steps) == 1
    assert again.steps[0].step_kind == "search"


def test_parse_task_plan_schema_kind():
    raw = json.dumps({
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {
                "status": "pending",
                "description": "Read",
                "step_kind": "read",
                "max_iterations": 3,
            }
        ],
    })
    parsed = parse_agent_response(raw, quiet=True, schema_kind="task_plan")
    assert parsed.get("steps")
    assert parsed["steps"][0]["step_kind"] == "read"


def test_reflect_schema_has_reasoning_only():
    schema = get_reflect_schema()
    assert "reasoning" in schema.get("properties", {})
    assert schema.get("required") == ["reasoning"]


def test_validate_tool_arguments_rejects_extra_keys():
    ok, err = validate_tool_arguments([
        {
            "name": "save_research_note",
            "arguments": {
                "task_name": "t",
                "gathered_data": "x",
                "format": "markdown",
            },
        },
    ])
    assert ok is False
    assert "format" in err or "validation" in err.lower()


def test_model_profile_heretic():
    p = resolve_model_output_profile("aquila_heretic")
    assert p.id == "heretic"


def test_format_attempts_includes_strict_first():
    schema = get_task_plan_schema()
    p = resolve_model_output_profile("aquila")
    attempts = format_attempts_for_profile(schema, p)
    assert isinstance(attempts[0], dict)


def test_shrink_schema_drops_descriptions():
    schema = build_strict_schema(
        {k: get_executable_tools()[k] for k in list(get_executable_tools())[:3]}
    )
    small = shrink_schema_for_retry(schema)
    assert "description" not in json.dumps(small)


def test_validate_tool_calls_normalized():
    ok, err = validate_tool_calls(
        normalize_tool_calls_list([{"name": "list_directory", "arguments": {"path": "."}}]),
        valid_names={"list_directory"},
    )
    assert ok, err
