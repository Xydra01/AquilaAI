"""Runtime settings setup_complete helpers."""
from __future__ import annotations

from agent.storage.runtime_settings import (
    is_setup_complete,
    mark_setup_complete,
    resolve_env_example_path,
)
from agent.storage.workspace_paths import REPO_ROOT


def test_setup_complete_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    assert is_setup_complete() is False
    mark_setup_complete()
    assert is_setup_complete() is True


def test_resolve_env_example_finds_example():
    path = resolve_env_example_path(REPO_ROOT)
    assert path.is_file()
