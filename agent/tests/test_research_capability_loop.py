"""Loop integration: capability schema and step adapter."""
from agent.capabilities.adapters import allowed_capabilities_for_step
from agent.parser.structured_schema import build_capability_action_json_schema


def test_capability_schema_size_bounded():
    allowed = allowed_capabilities_for_step("work", offline=False)
    schema = build_capability_action_json_schema(allowed)
    assert schema["properties"]["capabilities"]["maxItems"] == 1
    assert "reasoning" in schema["required"]
    assert len(allowed) <= 7


def test_capability_schema_is_flat_enum_not_anyof():
    """3.5 contract: flat id enum + freeform args — no anyOf/const branches.

    Embedding per-cap Pydantic trees in Ollama format is fragile; args are
    validated in run_capability. Schema+assistant prefill also causes HTTP 400.
    """
    allowed = allowed_capabilities_for_step("work", offline=True)
    schema = build_capability_action_json_schema(list(allowed))  # list must coerce
    items = schema["properties"]["capabilities"]["items"]
    assert "anyOf" not in items
    id_prop = items["properties"]["id"]
    assert "enum" in id_prop
    assert set(id_prop["enum"]) == set(allowed)
    assert items["properties"]["arguments"]["type"] == "object"
    assert items["properties"]["arguments"].get("additionalProperties") is True


def test_finalize_schema_requires_final_report():
    allowed = allowed_capabilities_for_step("finalize", is_final_step=True)
    schema = build_capability_action_json_schema(
        allowed,
        require_final_report=True,
    )
    assert "final_report" in schema["required"]


def test_offline_work_allowlist_excludes_gather():
    allowed = allowed_capabilities_for_step("work", offline=True)
    assert "cap.research.gather_web_sources@v1" not in allowed
    assert "cap.research.ingest_offline@v1" in allowed


def test_work_allowlist_includes_ingest_when_attachments():
    allowed = allowed_capabilities_for_step("work", offline=False, has_attachments=True)
    assert "cap.research.ingest_offline@v1" in allowed
    assert "cap.research.gather_web_sources@v1" in allowed


def test_default_capability_work_attachments():
    from agent.capabilities.adapters import default_capability_for_step

    cap = default_capability_for_step("work", offline=False, has_attachments=True)
    assert cap == "cap.research.ingest_offline@v1"


def test_resolve_recipe_offline():
    from agent.functions.research import resolve_recipe

    recipe = resolve_recipe("Research my journal only", offline=True)
    assert recipe.recipe_id == "fn.research.offline_pipeline"
