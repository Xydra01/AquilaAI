"""Tests for preferences persistence in app_settings.json."""
from __future__ import annotations

import json
import os

import pytest

from agent.storage.preferences import (
    apply_preferences_to_environ,
    load_preferences,
    save_preferences,
)


@pytest.fixture
def prefs_paths(tmp_path, monkeypatch):
    inst = tmp_path / "Agent-Instances"
    inst.mkdir(parents=True)

    def _agent_data_path(*parts):
        return tmp_path.joinpath(*parts) if parts else tmp_path

    monkeypatch.setattr(
        "agent.storage.runtime_settings.agent_data_path",
        _agent_data_path,
    )
    monkeypatch.setattr(
        "agent.storage.preferences.get_data_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "agent.storage.runtime_settings.get_data_root",
        lambda: tmp_path,
    )
    return inst


def test_save_and_load_preferences(prefs_paths):
    path = save_preferences(
        {"AQUILA_LIGHT_RESEARCH_USER_URL_READS": "4"},
        export_env=False,
    )
    assert path.is_file()
    prefs = load_preferences()
    assert prefs["AQUILA_LIGHT_RESEARCH_USER_URL_READS"] == "4"


def test_apply_preferences_to_environ(prefs_paths):
    save_preferences(
        {"AQUILA_LIGHT_RESEARCH_MAX_USER_URLS": "5"},
        export_env=False,
    )
    apply_preferences_to_environ()
    assert os.environ["AQUILA_LIGHT_RESEARCH_MAX_USER_URLS"] == "5"


def test_migrate_from_env_once(prefs_paths, monkeypatch):
    env_file = prefs_paths.parent / ".env"
    env_file.write_text(
        "AQUILA_LIGHT_RESEARCH_USER_URL_READS=6\n",
        encoding="utf-8",
    )
    prefs = load_preferences()
    assert prefs["AQUILA_LIGHT_RESEARCH_USER_URL_READS"] == "6"
    settings_path = prefs_paths / "app_settings.json"
    blob = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "preferences" in blob

    env_file.write_text("AQUILA_LIGHT_RESEARCH_USER_URL_READS=9\n", encoding="utf-8")
    prefs2 = load_preferences()
    assert prefs2["AQUILA_LIGHT_RESEARCH_USER_URL_READS"] == "6"


def test_export_to_env(prefs_paths):
    env_file = prefs_paths.parent / ".env"
    env_file.write_text("# existing\n", encoding="utf-8")
    save_preferences(
        {"AQUILA_LIGHT_RESEARCH_MAX_SEARCHES": "3"},
        export_env=True,
    )
    text = env_file.read_text(encoding="utf-8")
    assert "AQUILA_LIGHT_RESEARCH_MAX_SEARCHES=3" in text
