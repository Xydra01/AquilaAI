"""Tests for runtime_settings persistence."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.storage import (
    RuntimeSettings,
    engine_for_base_url,
    load_runtime_settings,
    prefer_model_for_engine,
    save_runtime_settings,
    set_engine,
)


def test_engine_for_base_url():
    assert engine_for_base_url("http://127.0.0.1:11435") == "tq"
    assert engine_for_base_url("http://127.0.0.1:11434") == "stock"
    assert engine_for_base_url("http://example.com:9999") is None


def test_save_and_load_runtime_settings(tmp_path, monkeypatch):
    inst = tmp_path / "Agent-Instances"
    inst.mkdir(parents=True)
    monkeypatch.setattr(
        "runtime_settings.agent_data_path",
        lambda *parts: inst.joinpath(*parts) if parts else inst,
    )
    settings = RuntimeSettings(
        ollama_engine="tq",
        ollama_base_url="http://127.0.0.1:11435",
        ollama_model="aquila-tq-64k",
        searxng_base_url="http://127.0.0.1:8080",
        searxng_engines="google,bing",
    )
    path = save_runtime_settings(settings, sync_env=False)
    assert path.is_file()
    loaded = load_runtime_settings()
    assert loaded.ollama_model == "aquila-tq-64k"
    assert loaded.searxng_engines == "google,bing"


def test_set_engine_updates_url():
    s = RuntimeSettings()
    set_engine(s, "tq")
    assert s.ollama_engine == "tq"
    assert "11435" in s.ollama_base_url


def test_resolve_model_tag_matches_base_name():
    from agent.storage import model_tag_matches, resolve_model_tag

    tags = ["aquila:latest", "aquila_heretic:latest"]
    assert resolve_model_tag("aquila", tags) == "aquila:latest"
    assert model_tag_matches("aquila", "aquila:latest")
    models = ["aquila_qwopus:latest", "aquila_heretic:latest", "aquila:latest", "aquila-tq-64k:latest"]
    stock_pick = prefer_model_for_engine(models, "stock")
    assert stock_pick == "aquila_qwopus:latest"
    assert "64k" in (prefer_model_for_engine(models, "tq") or "")
