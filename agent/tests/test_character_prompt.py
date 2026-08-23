import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import MODES_ROSTER, get_character_prompt, get_persona_build_prompt


def test_character_prompt_includes_bible_excludes_roster():
    init = "You are a pirate captain named Red."
    prefs = "User prefers short replies."
    prompt = get_character_prompt(init, prefs, "Red")
    assert init in prompt
    assert prefs in prompt
    assert "Red" in prompt
    assert MODES_ROSTER not in prompt
    assert "SINGLE valid JSON" not in prompt


def test_character_prompt_encourages_proactive_scene_agency():
    prompt = get_character_prompt("bible", "", "Red")
    assert "SCENE AGENCY" in prompt
    assert "assistant" in prompt.lower()
    assert "question" in prompt.lower()


def test_persona_build_prompt_mentions_capabilities():
    prompt = get_persona_build_prompt("- ignored tool docs -")
    assert "initialization.md" in prompt
    assert "cap.persona.write_initialization@v1" in prompt
    assert "cap.persona.finalize@v1" in prompt
    assert "capabilities" in prompt
    assert "tools" in prompt.lower()  # warns not to use tools array
    assert "scene agency" in prompt.lower()
