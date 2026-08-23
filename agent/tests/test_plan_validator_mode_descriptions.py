import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import mode_step_description, validate_and_tune_plan
from agent.core.plan_descriptions import TOOL_LEAK_TOKENS


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
    for tok in TOOL_LEAK_TOKENS:
        assert tok not in desc
    assert "cap.persona.ingest_sources@v1" in tuned["steps"][0]["description"]
    assert any("applied character_build" in n for n in notes)


def test_character_build_lore_search_description():
    desc = mode_step_description(
        "character_build", "search", "Emet-Selch", persona_research_lore=True
    )
    assert "cap.persona.gather_lore@v1" in desc
    assert "web_search" not in desc
    assert "nasa" not in desc.lower()
