import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from plan_validator import (
    BUDGET_RUBRIC,
    validate_and_tune_plan,
    infer_step_kind,
    get_step_kind_hint,
    tune_plan_json,
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
    assert parsed["steps"][0]["step_kind"] == "finalize"
    assert parsed["steps"][0]["max_iterations"] >= BUDGET_RUBRIC["finalize"][0]


def test_step_kind_hint_nonempty():
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
