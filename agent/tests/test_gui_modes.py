"""Instance default_mode ↔ workspace mode selector alignment."""
import importlib

import agent.gui.gui_modes as gui_modes
from agent.gui.gui_modes import (
    INSTANCE_DEFAULT_MODE_IDS,
    WORKSPACE_MODE_FLAGS,
    normalize_default_mode_id,
    workspace_label_for_default_mode,
)


def _reload_gui_modes(monkeypatch, *, data_enabled: bool | None = None):
    if data_enabled is None:
        monkeypatch.delenv("AQUILA_ENABLE_DATA_PROCESSING", raising=False)
    else:
        monkeypatch.setenv(
            "AQUILA_ENABLE_DATA_PROCESSING", "1" if data_enabled else "0"
        )
    importlib.reload(gui_modes)


def test_data_mode_disabled_by_default(monkeypatch):
    _reload_gui_modes(monkeypatch, data_enabled=False)
    assert "data" not in gui_modes.INSTANCE_DEFAULT_MODE_IDS
    assert "Data Processing" not in gui_modes.WORKSPACE_MODE_FLAGS
    assert gui_modes.normalize_default_mode_id("data") == "chat"
    assert gui_modes.workspace_label_for_default_mode("data") == "Chat Mode"


def test_data_mode_enabled_when_env_set(monkeypatch):
    _reload_gui_modes(monkeypatch, data_enabled=True)
    assert "data" in gui_modes.INSTANCE_DEFAULT_MODE_IDS
    assert gui_modes.WORKSPACE_MODE_FLAGS.get("Data Processing") == "data"


def test_learn_in_instance_and_workspace_modes():
    assert "learn" in INSTANCE_DEFAULT_MODE_IDS
    assert "Learn Mode" in WORKSPACE_MODE_FLAGS
    assert WORKSPACE_MODE_FLAGS["Learn Mode"] == "learn"


def test_workspace_label_from_short_id():
    assert workspace_label_for_default_mode("learn") == "Learn Mode"


def test_workspace_label_from_label():
    assert workspace_label_for_default_mode("Learn Mode") == "Learn Mode"


def test_normalize_default_mode_id():
    assert normalize_default_mode_id("Learn Mode") == "learn"
    assert normalize_default_mode_id("learn") == "learn"
