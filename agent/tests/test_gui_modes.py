"""Instance default_mode ↔ workspace mode selector alignment."""
from gui_modes import (
    INSTANCE_DEFAULT_MODE_IDS,
    WORKSPACE_MODE_FLAGS,
    normalize_default_mode_id,
    workspace_label_for_default_mode,
)


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
