"""Foundation tests for capability registry and research settings."""
import os

import pytest


def test_capability_registry_lists_research_caps():
    from agent.capabilities import list_capabilities, get_capability

    caps = list_capabilities(mode="research")
    ids = {c.capability_id for c in caps}
    assert "cap.web.search@v1" in ids
    assert "cap.research.gather_web_sources@v1" in ids
    assert get_capability("cap.research.finalize_deliverable@v1") is not None


def test_run_capability_unknown():
    from agent.capabilities import run_capability
    from agent.capabilities.base import CapabilityContext

    ctx = CapabilityContext(task_id="t1")
    result = run_capability("cap.nope@v1", ctx, {})
    assert not result.ok
    assert result.error_code == "unknown_capability"


def test_research_recipe_strict_default_off(monkeypatch):
    monkeypatch.delenv("AQUILA_RESEARCH_RECIPE_STRICT", raising=False)
    from agent.core.loop_settings import research_recipe_strict_enabled

    assert research_recipe_strict_enabled() is False


def test_research_recipe_strict_on(monkeypatch):
    monkeypatch.setenv("AQUILA_RESEARCH_RECIPE_STRICT", "1")
    from importlib import reload
    import agent.core.loop_settings as ls

    reload(ls)
    assert ls.research_recipe_strict_enabled() is True


def test_attach_capability_ids_to_plan():
    from agent.capabilities.adapters import attach_capability_ids_to_plan

    plan = {
        "steps": [
            {"step_kind": "search", "description": "Find sources"},
            {"step_kind": "finalize", "description": "Write report"},
        ]
    }
    attach_capability_ids_to_plan(plan, offline=False)
    assert plan["steps"][0]["capability_id"] == "cap.research.gather_web_sources@v1"
    assert plan["steps"][1]["capability_id"] == "cap.research.finalize_deliverable@v1"
