import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import mode_step_description, validate_and_tune_plan


def test_character_build_read_step_has_no_nasa():
    plan = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [
            {
                "description": "Read NASA .gov sources for exoplanets",
                "step_kind": "read",
                "max_iterations": 5,
            },
            {"description": "synth", "step_kind": "synthesize", "max_iterations": 6},
            {"description": "fin", "step_kind": "finalize", "max_iterations": 6},
        ],
    }
    tuned, notes = validate_and_tune_plan(
        plan, "character_build", "Emet-Selch", persona_research_lore=False
    )
    desc = tuned["steps"][0]["description"].lower()
    assert "nasa" not in desc
    assert ".gov" not in desc
    assert "save_research_note" in desc
    assert any("applied character_build" in n for n in notes)


def test_character_build_lore_search_description():
    desc = mode_step_description(
        "character_build", "search", "Emet-Selch", persona_research_lore=True
    )
    assert "web_search" in desc
    assert "nasa" not in desc.lower()
