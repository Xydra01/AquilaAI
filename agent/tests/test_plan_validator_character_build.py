import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from plan_validator import expand_character_build_plan, validate_and_tune_plan


def test_character_build_plan_gets_read_synthesize_finalize_kinds():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {
                "description": "Ingest lore and write init doc",
                "step_kind": "read",
                "max_iterations": 5,
            },
            {
                "description": "Web search",
                "step_kind": "search",
                "max_iterations": 4,
            },
            {
                "description": "Finalize persona",
                "step_kind": "write",
                "max_iterations": 6,
            },
        ],
    }
    tuned, _notes = validate_and_tune_plan(plan, "character_build", "Build Horror Sans")
    kinds = [s["step_kind"] for s in tuned["steps"]]
    assert kinds == ["read", "synthesize", "finalize"]


def test_expand_character_build_plan_replaces_four_step_legacy():
    plan = {
        "status": "in_progress",
        "current_step_index": 2,
        "steps": [
            {"description": "read and write init", "step_kind": "read", "max_iterations": 7},
            {"description": "search lore", "step_kind": "search", "max_iterations": 4},
            {"description": "write init", "step_kind": "write", "max_iterations": 5},
            {"description": "done", "step_kind": "finalize", "max_iterations": 4},
        ],
    }
    expanded, note = expand_character_build_plan(plan, "Horror Sans")
    assert "Expanded character_build" in note
    assert len(expanded["steps"]) == 3
    assert expanded["current_step_index"] == 0
    kinds = [s["step_kind"] for s in expanded["steps"]]
    assert kinds == ["read", "synthesize", "finalize"]


def test_expand_character_build_plan_with_lore_four_steps():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "one", "step_kind": "read", "max_iterations": 4},
        ],
    }
    expanded, note = expand_character_build_plan(
        plan, "Horror Sans", persona_research_lore=True
    )
    assert "Expanded character_build" in note
    assert len(expanded["steps"]) == 4
    kinds = [s["step_kind"] for s in expanded["steps"]]
    assert kinds == ["search", "read", "synthesize", "finalize"]


def test_validate_expands_legacy_four_step_character_build():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {"description": "Ingest and write init", "step_kind": "read", "max_iterations": 7},
            {"description": "Extra", "step_kind": "search", "max_iterations": 4},
            {"description": "More", "step_kind": "code", "max_iterations": 5},
            {"description": "Done", "step_kind": "finalize", "max_iterations": 4},
        ],
    }
    tuned, notes = validate_and_tune_plan(plan, "character_build", "Horror Sans")
    assert any("Expanded character_build" in n for n in notes)
    assert len(tuned["steps"]) == 3
