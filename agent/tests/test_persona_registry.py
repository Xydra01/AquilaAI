import json

import pytest

from instance_registry import create_instance, ensure_default_instance
from persona_registry import (
    Persona,
    chat_history_path,
    create_persona,
    delete_persona,
    get_persona,
    list_personas,
    load_chat_history,
    load_initialization_doc,
    load_user_preferences,
    save_chat_history,
    save_persona,
    initialization_path,
)


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    ensure_default_instance()
    yield


def test_persona_crud_under_instance():
    inst = create_instance("CAI Tester", default_mode="character")
    p = create_persona(inst.id, "Aria", "A curious starship pilot.", build_complete=True)
    assert p.id
    assert get_persona(inst.id, p.id) is not None
    listed = list_personas(inst.id)
    assert any(x.id == p.id for x in listed)
    p.tagline = "Explorer"
    save_persona(inst.id, p)
    again = get_persona(inst.id, p.id)
    assert again.tagline == "Explorer"
    assert delete_persona(inst.id, p.id)
    assert get_persona(inst.id, p.id) is None


def test_chat_history_round_trip():
    inst = create_instance("Hist", default_mode="character")
    p = create_persona(inst.id, "Bot", build_complete=True)
    msgs = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello there."},
    ]
    save_chat_history(inst.id, p.id, msgs)
    loaded = load_chat_history(inst.id, p.id)
    assert loaded == msgs
    assert chat_history_path(inst.id, p.id).is_file()


def test_initialization_and_preferences_paths():
    inst = create_instance("Paths", default_mode="character")
    p = create_persona(inst.id, "Doc", build_complete=False)
    init = initialization_path(inst.id, p.id)
    init.write_text("# Bible\n" + ("x" * 900), encoding="utf-8")
    assert "Bible" in load_initialization_doc(inst.id, p.id)
    prefs = load_user_preferences(inst.id, p.id)
    assert "preferences" in prefs.lower()
