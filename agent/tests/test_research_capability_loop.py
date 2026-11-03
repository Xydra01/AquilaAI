"""Loop integration: capability schema and step adapter."""
import pytest

from agent.capabilities.adapters import allowed_capabilities_for_step
from agent.parser.structured_schema import build_capability_action_json_schema


@pytest.fixture(autouse=True)
def _clear_capability_schema_cache():
    from agent.parser import structured_schema as ss

    ss._capability_action_schema_cache.clear()
    yield
    ss._capability_action_schema_cache.clear()


def test_capability_schema_size_bounded():
    allowed = allowed_capabilities_for_step("work", offline=False)
    schema = build_capability_action_json_schema(allowed)
    assert schema["properties"]["capabilities"]["maxItems"] == 1
    assert "reasoning" in schema["required"]
    assert len(allowed) <= 7


def test_capability_schema_flat_when_enrich_disabled(monkeypatch):
    """Flat id enum + freeform args when enrichment is disabled."""
    monkeypatch.setenv("AQUILA_CAPABILITY_SCHEMA_ENRICH", "0")
    allowed = allowed_capabilities_for_step("work", offline=True)
    schema = build_capability_action_json_schema(list(allowed))  # list must coerce
    items = schema["properties"]["capabilities"]["items"]
    assert "anyOf" not in items
    id_prop = items["properties"]["id"]
    assert "enum" in id_prop
    assert set(id_prop["enum"]) == set(allowed)
    assert items["properties"]["arguments"]["type"] == "object"
    assert items["properties"]["arguments"].get("additionalProperties") is True


def test_capability_schema_enriched_when_small_allowlist(monkeypatch):
    """Research search has 2 action caps — Tier A anyOf branches with typed args."""
    monkeypatch.setenv("AQUILA_CAPABILITY_SCHEMA_ENRICH", "1")
    allowed = allowed_capabilities_for_step("search", offline=True)
    from agent.capabilities.adapters import PLAN_CHECKLIST_CAP_IDS

    schema = build_capability_action_json_schema(
        allowed,
        action_cap_ids=allowed - PLAN_CHECKLIST_CAP_IDS,
    )
    items = schema["properties"]["capabilities"]["items"]
    assert "anyOf" in items
    assert len(items["anyOf"]) == len(allowed)
    create_like = next(
        (
            b
            for b in items["anyOf"]
            if "gather_web_sources" in str(b["properties"]["id"].get("const", ""))
        ),
        None,
    )
    assert create_like is not None
    args = create_like["properties"]["arguments"]
    assert "properties" in args


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
