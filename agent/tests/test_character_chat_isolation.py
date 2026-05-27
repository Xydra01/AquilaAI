import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui_pages.character_page import CharacterPage
from instance_registry import create_instance, ensure_default_instance
from persona_registry import create_persona, load_chat_history, save_chat_history


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    ensure_default_instance()
    yield


def test_character_persist_does_not_touch_global_chat_history():
    # Avoid constructing the full Qt UI (can require a QApplication). We only need the
    # persistence behavior of CharacterPage.persist_character_turn.
    class DummyWin:
        def __init__(self):
            self._chat_history_messages = [
                {"role": "user", "content": "global chat"},
                {"role": "assistant", "content": "global reply"},
            ]
            self.active_instance_id = "default"

    win = DummyWin()
    page = CharacterPage.__new__(CharacterPage)
    page.main = win
    inst = create_instance("Iso", default_mode="character")
    win.active_instance_id = inst.id
    p = create_persona(inst.id, "IsoChar", build_complete=True)
    page._active_persona = p
    page._persona_history = []
    page._user_turn_count = 0

    page.persist_character_turn("in character", "reply in character")

    assert len(win._chat_history_messages) == 2
    assert win._chat_history_messages[0]["content"] == "global chat"
    loaded = load_chat_history(inst.id, p.id)
    assert len(loaded) == 2
    assert loaded[0]["content"] == "in character"
