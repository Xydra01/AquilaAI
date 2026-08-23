"""Tests for packaged install path resolution."""
from __future__ import annotations

import os
import sys

import pytest

from agent.aquila_runtime.paths import (
    get_default_data_root,
    get_install_root,
    is_frozen,
    launch_mode,
)
from agent.storage.workspace_paths import get_data_root


def test_launch_mode_dev_by_default(monkeypatch):
    monkeypatch.delenv("AQUILA_LAUNCH_MODE", raising=False)
    monkeypatch.setattr("agent.aquila_runtime.paths.is_frozen", lambda: False)
    assert launch_mode() == "dev"


def test_launch_mode_packaged_when_frozen(monkeypatch):
    monkeypatch.setattr("agent.aquila_runtime.paths.is_frozen", lambda: True)
    assert launch_mode() == "packaged"


def test_frozen_data_root_uses_app_data(monkeypatch, tmp_path):
    monkeypatch.delenv("AQUILA_DATA_ROOT", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        "agent.aquila_runtime.paths.get_default_data_root",
        lambda: tmp_path / "Aquila",
    )
    assert get_data_root() == tmp_path / "Aquila"


def test_data_root_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path / "custom"))
    assert get_data_root() == (tmp_path / "custom").resolve()


def test_install_root_dev_is_repo():
    if is_frozen():
        pytest.skip("dev-only")
    root = get_install_root()
    assert (root / "agent").is_dir()
