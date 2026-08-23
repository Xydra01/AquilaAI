import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    BUDGET_RUBRIC,
    expand_dynamic_research_plan,
    expand_research_plan,
    expand_offline_research_plan,
    expand_dynamic_offline_research_plan,
    validate_and_tune_plan,
    infer_step_kind,
    get_step_kind_hint,
    tune_plan_json,
    is_degenerate_description,
    sanitize_step_description,
)


def test_clamps_under_budget_steps():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "Search the web for pricing", "max_iterations": 1},
        ],
    }
    tuned, notes = validate_and_tune_plan(plan, "research")
    assert tuned["steps"][0]["max_iterations"] >= BUDGET_RUBRIC["search"][0]
    assert tuned["steps"][0]["step_kind"] == "search"
    assert any("max_iterations" in n for n in notes)


def test_infers_code_kind():
    kind = infer_step_kind("Create hello.py and run it", "task", 0, 3)
    assert kind == "code"


def test_caps_total_steps():
    steps = [{"description": f"Step {i}", "max_iterations": 3} for i in range(12)]
    plan = {"status": "in_progress", "current_step_index": 0, "steps": steps}
    tuned, notes = validate_and_tune_plan(plan, "task")
    assert len(tuned["steps"]) == 8
    assert any("Trimmed" in n for n in notes)


def test_tune_plan_json_roundtrip():
    raw = json.dumps({
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Final report", "max_iterations": 1}],
    })
    out, notes = tune_plan_json(raw, "research")
    parsed = json.loads(out)
    assert len(parsed["steps"]) >= 4
    assert parsed["steps"][-1]["step_kind"] == "finalize"
    assert parsed["steps"][-1]["max_iterations"] >= BUDGET_RUBRIC["finalize"][0]


def test_step_kind_hint_nonempty():
    assert "web_search" in get_step_kind_hint("search")


def test_step_kind_hint_research_mode_capability_first():
    hint = get_step_kind_hint("search", mode="research")
    assert "cap.research" in hint
    assert "web_search" not in hint
    assert "finish_task" not in get_step_kind_hint("finalize", mode="research")


def test_step_kind_hint_default_unchanged_for_code():
    assert "run_pytest" in get_step_kind_hint("tdd_red")
    assert "web_search" in get_step_kind_hint("search")


def test_code_mode_tdd_hint_note():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Do thing", "max_iterations": 3}],
    }
    _, notes = validate_and_tune_plan(plan, "code", "implement a new feature with pytest")
    assert any("TDD" in n for n in notes)


def test_tdd_step_kinds_in_rubric():
    assert "tdd_red" in BUDGET_RUBRIC
    assert "run_pytest" in get_step_kind_hint("tdd_red")


def test_expand_research_plan_produces_four_steps():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Do everything at once", "max_iterations": 4}],
    }
    expanded, note = expand_research_plan(plan, "Earth-like exoplanets")
    assert len(expanded["steps"]) == 4
    kinds = [s["step_kind"] for s in expanded["steps"]]
    assert kinds == ["search", "read", "synthesize", "finalize"]
    assert "Expanded" in note


def test_validate_expands_single_step_research_plan():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Research topic", "max_iterations": 2}],
    }
    tuned, notes = validate_and_tune_plan(plan, "research", "exoplanets")
    assert len(tuned["steps"]) >= 4
    assert any("Expanded" in n for n in notes)


def test_is_degenerate_description_detects_repetition_loop():
    garbage = "mass, " + ", ".join(["radius"] * 80) + ", finalize"
    assert is_degenerate_description(garbage) is True


def test_sanitize_replaces_degenerate_description():
    garbage = "read, " + ", ".join(["read"] * 50)
    clean, modified = sanitize_step_description(
        garbage, step_kind="read", step_index=1, total_steps=4
    )
    assert modified is True
    assert "read_webpage" in clean or "extract" in clean.lower()
    assert len(clean) <= 700


def test_research_four_step_kinds_by_index():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "Search NASA sources", "max_iterations": 4},
            {"description": "read, " + ", ".join(["read"] * 40), "max_iterations": 5},
            {"description": "Synthesize report", "max_iterations": 6},
            {"description": "Final deliverable", "max_iterations": 6},
        ],
    }
    tuned, notes = validate_and_tune_plan(plan, "research", "exoplanets")
    kinds = [s["step_kind"] for s in tuned["steps"]]
    assert kinds == ["search", "read", "synthesize", "finalize"]
    assert any("sanitized" in n for n in notes)
    assert len(tuned["steps"][1]["description"]) < 700


def test_expand_omits_explore_note_when_brief_ran():
    plan = {"steps": [{"description": "x"}]}
    expanded, note = expand_research_plan(
        plan, "topic", explore_brief_ran=True
    )
    assert "Explore brief already ran" in note
    assert expanded["steps"][0]["step_kind"] == "search"


def test_expand_dynamic_research_plan_two_steps(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    plan = {"steps": [{"description": "Research AI safety"}]}
    expanded, note = expand_dynamic_research_plan(plan, "AI safety")
    assert len(expanded["steps"]) == 2
    assert [s["step_kind"] for s in expanded["steps"]] == ["work", "finalize"]
    assert expanded.get("dynamic_plan") is True
    assert "Dynamic" in note


def test_validate_uses_dynamic_plan_when_flag_on(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Research topic", "max_iterations": 2}],
    }
    tuned, notes = validate_and_tune_plan(plan, "research", "exoplanets")
    kinds = [s["step_kind"] for s in tuned["steps"]]
    assert kinds == ["work", "finalize"]
    assert any("Dynamic" in n for n in notes)


def test_expand_offline_research_plan_three_steps():
    plan = {"steps": [{"description": "x"}]}
    expanded, note = expand_offline_research_plan(plan, "local topic")
    assert len(expanded["steps"]) == 3
    assert [s["step_kind"] for s in expanded["steps"]] == [
        "read",
        "synthesize",
        "finalize",
    ]
    assert expanded.get("offline_research") is True
    assert "Offline" in note


def test_validate_offline_research_plan(monkeypatch):
    monkeypatch.delenv("AQUILA_DYNAMIC_LOOP", raising=False)
    plan = {"steps": [{"description": "Research from PDFs"}]}
    tuned, notes = validate_and_tune_plan(
        plan, "research", "hornworm diet", offline_research=True
    )
    kinds = [s["step_kind"] for s in tuned["steps"]]
    assert kinds == ["read", "synthesize", "finalize"]
    assert any("Offline" in n for n in notes)


def test_validate_offline_dynamic_research_plan(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    plan = {"steps": [{"description": "Research from attachments"}]}
    tuned, notes = validate_and_tune_plan(
        plan, "research", "local notes", offline_research=True
    )
    kinds = [s["step_kind"] for s in tuned["steps"]]
    assert kinds == ["work", "finalize"]
    assert tuned.get("offline_research") is True
    assert any("offline" in n.lower() for n in notes)
