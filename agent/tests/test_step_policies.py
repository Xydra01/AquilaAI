import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import CharacterBuildPolicy, get_step_policy


def test_character_build_blocks_write_on_search():
    policy = CharacterBuildPolicy(
        mode="character_build", step_kind="search", persona_research_lore=True
    )
    msg = policy.block_message("write_persona_file", tools_succeeded=set())
    assert msg is not None
    assert "synthesize" in msg


def test_get_step_policy_character():
    p = get_step_policy("character_build", "read", persona_research_lore=True)
    assert isinstance(p, CharacterBuildPolicy)
