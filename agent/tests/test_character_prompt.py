import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from prompts import MODES_ROSTER, get_character_prompt, get_persona_build_prompt


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


def test_persona_build_prompt_mentions_tools():
    prompt = get_persona_build_prompt("- `write_persona_file(path, content)`: write")
    assert "initialization.md" in prompt
    assert "finalize_persona" in prompt
    assert "write_persona_file" in prompt
    assert "Scene agency" in prompt
