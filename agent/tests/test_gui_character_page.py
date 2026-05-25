import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

import gui
from gui_pages.character_page import CharacterPage
from instance_registry import create_instance, ensure_default_instance
from persona_registry import create_persona, save_chat_history


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    ensure_default_instance()
    yield


def test_mode_flags_include_character():
    assert "Character Mode" in gui.MODE_FLAGS
    assert gui.MODE_FLAGS["Character Mode"] == "character"


def test_character_page_history_round_trip(qtbot, qapp, tmp_path, monkeypatch):
    win = gui.AquilaOS()
    page = win.character_page
    inst = create_instance("GUI CAI", default_mode="character")
    win.active_instance_id = inst.id
    p = create_persona(inst.id, "TestChar", build_complete=True)
    p.greeting = "Hi!"
    from persona_registry import save_persona

    save_persona(inst.id, p)
    save_chat_history(inst.id, p.id, [{"role": "user", "content": "Hey"}])
    page._open_chat(p)
    assert page.is_streaming_character_chat()
    hist = page.get_persona_chat_history()
    assert hist and hist[0]["content"] == "Hey"
