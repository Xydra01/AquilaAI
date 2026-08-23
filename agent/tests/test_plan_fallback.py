import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.plan_validator import (
    build_fallback_research_plan,
    research_plan_min_steps,
    validate_and_tune_plan,
)


def test_research_plan_min_steps_default(monkeypatch):
    monkeypatch.delenv("AQUILA_DYNAMIC_LOOP", raising=False)
    assert research_plan_min_steps() == 4


def test_research_plan_min_steps_dynamic(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    assert research_plan_min_steps() == 2


def test_build_fallback_research_plan_offline(monkeypatch):
    monkeypatch.delenv("AQUILA_DYNAMIC_LOOP", raising=False)
    plan, note = build_fallback_research_plan(
        "Summarize attached PDFs",
        offline_research=True,
    )
    assert "Recipe fallback" in note
    assert plan.get("planner_fallback") is True
    tuned, _ = validate_and_tune_plan(
        plan, "research", "Summarize attached PDFs", offline_research=True
    )
    assert len(tuned["steps"]) >= 3
    assert tuned["steps"][-1]["step_kind"] == "finalize"
    assert tuned.get("capability_recipe")
    assert all(s.get("capability_id") for s in tuned["steps"])


def test_build_fallback_research_plan_serializes(monkeypatch):
    monkeypatch.delenv("AQUILA_DYNAMIC_LOOP", raising=False)
    plan, _ = build_fallback_research_plan("Exoplanet habitability survey")
    payload = json.loads(json.dumps(plan))
    assert payload["steps"]


def test_salvage_oversized_plan_trims_descriptions():
    from agent.core.plan_validator import salvage_oversized_plan

    bloated = {
        "status": "in_progress",
        "user_goal": "x" * 800,
        "steps": [
            {
                "description": "y" * 500,
                "step_kind": "search",
                "max_iterations": 4,
            }
        ],
    }
    out = salvage_oversized_plan(bloated)
    assert len(out["user_goal"]) <= 400
    assert len(out["steps"][0]["description"]) <= 200
