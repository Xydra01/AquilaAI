"""Whether to show the first-run setup wizard."""
from __future__ import annotations

import os

from agent.aquila_runtime.paths import is_frozen
from agent.storage.runtime_settings import is_setup_complete


def should_show_setup_wizard() -> bool:
    if is_setup_complete():
        return False
    if is_frozen():
        return True
    flag = os.getenv("AQUILA_SHOW_SETUP_WIZARD", "").strip().lower()
    return flag in ("1", "true", "yes", "on")
