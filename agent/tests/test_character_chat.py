import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from instance_registry import create_instance, ensure_default_instance
from main import Agent
from persona_registry import create_persona, initialization_path


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    ensure_default_instance()
    yield


def test_run_character_chat_injects_init_doc(monkeypatch):
    inst = create_instance("Chat", default_mode="character")
    p = create_persona(inst.id, "Mira", build_complete=True)
    init = initialization_path(inst.id, p.id)
    init.write_text("Mira speaks in riddles." * 50, encoding="utf-8")

    captured = {}

    def fake_chat(messages, temperature=0.8, stream=True):
        captured["messages"] = messages
        captured["temperature"] = temperature
        if stream:
            yield {"message": {"content": "..."}}
        return {"message": {"content": "..."}}

    agent = Agent(instance_id=inst.id)
    agent.client = MagicMock()
    agent.client.chat = fake_chat

    list(agent.run_character_chat(p, "Hello?", [], stream=True))
    system = captured["messages"][0]["content"]
    assert "Mira speaks in riddles" in system
    assert "MODES_ROSTER" not in system
    assert captured["temperature"] == pytest.approx(0.8, abs=0.01)


def test_run_character_chat_includes_text_attachments(monkeypatch):
    inst = create_instance("Chat", default_mode="character")
    p = create_persona(inst.id, "Mira", build_complete=True)
    init = initialization_path(inst.id, p.id)
    init.write_text("Mira speaks in riddles." * 50, encoding="utf-8")

    captured = {}

    def fake_chat(messages, temperature=0.8, stream=True):
        captured["messages"] = messages
        if stream:
            yield {"message": {"content": "ok"}}
        return {"message": {"content": "ok"}}

    agent = Agent(instance_id=inst.id)
    agent.client = MagicMock()
    agent.client.chat = fake_chat

    list(
        agent.run_character_chat(
            p,
            "What is in the file?",
            [],
            text_chunks=["SECRET_LORE_CHUNK"],
            stream=True,
        )
    )
    user_msg = captured["messages"][-1]["content"]
    assert "SECRET_LORE_CHUNK" in user_msg
    assert "ATTACHED CONTEXT" in user_msg


def test_run_character_chat_passes_vision_payload(monkeypatch):
    inst = create_instance("Chat", default_mode="character")
    p = create_persona(inst.id, "Mira", build_complete=True)
    init = initialization_path(inst.id, p.id)
    init.write_text("Mira speaks in riddles." * 50, encoding="utf-8")

    captured = {}

    def fake_chat(messages, temperature=0.8, stream=True):
        captured["messages"] = messages
        if stream:
            yield {"message": {"content": "ok"}}
        return {"message": {"content": "ok"}}

    agent = Agent(instance_id=inst.id)
    agent.client = MagicMock()
    agent.client.chat = fake_chat

    list(
        agent.run_character_chat(
            p,
            "Look",
            [],
            image_payloads=["data:image/jpeg;base64,abc123"],
            stream=True,
        )
    )
    content = captured["messages"][-1]["content"]
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"
    assert "abc123" in content[1]["image_url"]["url"]
