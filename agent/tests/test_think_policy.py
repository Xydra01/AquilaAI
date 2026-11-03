import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import resolve_thinking_policy


def test_think_disabled_master_switch(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "0")
    p = resolve_thinking_policy(surface="chat", model_name="qwen3.5:9b")
    assert p.think is False


def test_think_enabled_qwen_chat(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat,act")
    p = resolve_thinking_policy(
        surface="chat", model_name="aquila_heretic", estimated_prompt_tokens=1000
    )
    assert p.think is True
    assert p.enabled is True


def test_think_surface_not_listed(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    p = resolve_thinking_policy(surface="act", model_name="aquila_heretic")
    assert p.think is False


def test_force_disabled(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    p = resolve_thinking_policy(
        surface="act", model_name="aquila_heretic", force_disabled=True
    )
    assert p.think is False


def test_think_disabled_when_json_schema(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "act")
    p = resolve_thinking_policy(
        surface="act",
        model_name="aquila:latest",
        has_format_schema=True,
    )
    assert p.think is False


def test_reflect_surface_enabled(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "reflect")
    p = resolve_thinking_policy(surface="reflect", model_name="aquila:latest")
    assert p.think is True


def test_stock_aquila_enables_think(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    p = resolve_thinking_policy(
        surface="chat", model_name="aquila", estimated_prompt_tokens=1000
    )
    assert p.think is True


def test_aquila_qwopus_enables_think(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    p = resolve_thinking_policy(
        surface="chat", model_name="aquila_qwopus", estimated_prompt_tokens=1000
    )
    assert p.think is True


def test_think_complexity_gate_short_prompt(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    monkeypatch.setenv("AQUILA_THINK_MIN_TOKENS", "800")
    p = resolve_thinking_policy(
        surface="chat", model_name="aquila_qwopus", estimated_prompt_tokens=100
    )
    assert p.think is False


def test_think_complexity_gate_long_prompt(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    monkeypatch.setenv("AQUILA_THINK_MIN_TOKENS", "800")
    p = resolve_thinking_policy(
        surface="chat", model_name="aquila_qwopus", estimated_prompt_tokens=1200
    )
    assert p.think is True


def test_aquila_nsfw_disables_think(monkeypatch):
    """Llama/Hermes GGUF tags must not get think:true (Ollama HTTP 400)."""
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    for name in ("aquila_NSFW", "Aquila_NSFW:latest"):
        p = resolve_thinking_policy(surface="chat", model_name=name)
        assert p.think is False, name
