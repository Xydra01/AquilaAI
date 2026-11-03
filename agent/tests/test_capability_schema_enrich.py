"""Tier A/B capability argument schema enrichment."""
from __future__ import annotations

import pytest

from agent.capabilities.adapters import (
    PLAN_CHECKLIST_CAP_IDS,
    allowed_capabilities_for_step,
)
from agent.capabilities.schema_hints import format_capability_argument_hints
from agent.parser.structured_schema import (
    build_capability_action_json_schema,
    prepare_capability_input_schema,
)


@pytest.fixture(autouse=True)
def _clear_capability_schema_cache():
    from agent.parser import structured_schema as ss

    ss._capability_action_schema_cache.clear()
    yield
    ss._capability_action_schema_cache.clear()


def test_prepare_capability_input_schema_create_file():
    schema = prepare_capability_input_schema("cap.dev.create_file@v1")
    assert schema is not None
    props = schema.get("properties") or {}
    assert "file_path" in props
    assert "content" in props
    assert "file_path" in (schema.get("required") or [])
    assert "content" in (schema.get("required") or [])


def test_code_allowlist_empty_after_phase3():
    """Phase 3: LoopEngine code allowlists are frozen empty."""
    assert allowed_capabilities_for_step("tdd_red", mode="code") == frozenset()
    assert allowed_capabilities_for_step("work", mode="code") == frozenset()


def test_writing_work_gets_enriched_schema(monkeypatch):
    monkeypatch.setenv("AQUILA_CAPABILITY_SCHEMA_ENRICH", "1")
    allowed = allowed_capabilities_for_step("write", mode="writing")
    action_ids = allowed - PLAN_CHECKLIST_CAP_IDS
    schema = build_capability_action_json_schema(
        allowed,
        action_cap_ids=action_ids,
    )
    items = schema["properties"]["capabilities"]["items"]
    assert "properties" in items or "anyOf" in items


def test_format_capability_argument_hints_lists_required_fields():
    text = format_capability_argument_hints(["cap.dev.create_file@v1"], max_caps=1)
    assert "cap.dev.create_file@v1" in text
    assert "file_path" in text
    assert "content" in text
    assert "required" in text


def test_enriched_create_file_branch_requires_content(monkeypatch):
    monkeypatch.setenv("AQUILA_CAPABILITY_SCHEMA_ENRICH", "1")
    allowed = frozenset({"cap.dev.create_file@v1"})
    schema = build_capability_action_json_schema(
        allowed,
        action_cap_ids=allowed,
    )
    items = schema["properties"]["capabilities"]["items"]
    branch = next(
        b
        for b in items["anyOf"]
        if b["properties"]["id"].get("const") == "cap.dev.create_file@v1"
    )
    args = branch["properties"]["arguments"]
    assert "content" in (args.get("required") or [])


def test_capability_schema_flat_when_enrich_disabled(monkeypatch):
    monkeypatch.setenv("AQUILA_CAPABILITY_SCHEMA_ENRICH", "0")
    allowed = allowed_capabilities_for_step("search", offline=True)
    schema = build_capability_action_json_schema(allowed)
    items = schema["properties"]["capabilities"]["items"]
    assert "anyOf" not in items
    assert items["properties"]["arguments"].get("additionalProperties") is True


def test_slot_fill_schema_has_no_capability_id(monkeypatch):
    from agent.parser.structured_schema import build_capability_slot_fill_schema

    schema = build_capability_slot_fill_schema("cap.dev.create_file@v1")
    props = schema.get("properties") or {}
    assert "capabilities" not in props
    assert "arguments" in props
    args = props["arguments"]
    assert "file_path" in (args.get("properties") or {})
    assert "content" in (args.get("properties") or {})
    assert "file_path" in (args.get("required") or [])
    assert "content" in (args.get("required") or [])
