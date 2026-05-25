import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gui
from instance_registry import create_instance, ensure_default_instance
from persona_registry import create_persona, initialization_path


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    ensure_default_instance()
    yield


def test_agent_worker_character_passes_attachments():
    inst = create_instance("W", default_mode="character")
    p = create_persona(inst.id, "Mira", build_complete=True)
    init = initialization_path(inst.id, p.id)
    init.write_text("x" * 900, encoding="utf-8")

    def fake_run_character_chat(persona, user_input, chat_history, **kwargs):
        fake_run_character_chat.called_kwargs = kwargs
        yield {"message": {"content": "hi"}}

    mock_agent = MagicMock()
    mock_agent.run_character_chat.side_effect = fake_run_character_chat

    worker = gui.AgentWorker(
        "chat",
        "Look",
        "character",
        attached_chunks=["LORE"],
        attached_images=["data:image/jpeg;base64,abc"],
        chat_history=[],
        instance_id=inst.id,
        persona_id=p.id,
    )
    with patch("gui.get_agent", return_value=mock_agent):
        worker.run()

    kw = fake_run_character_chat.called_kwargs
    assert kw["text_chunks"] == ["LORE"]
    assert kw["image_payloads"] == ["data:image/jpeg;base64,abc"]
