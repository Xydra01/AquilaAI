"""Shared mode identifiers for instance defaults (home) and workspace selector (gui)."""
from __future__ import annotations

# Short ids stored on AquilaInstance.default_mode (home screen combo).
INSTANCE_DEFAULT_MODE_IDS: tuple[str, ...] = (
    "chat",
    "research",
    "code",
    "writing",
    "character",
    "learn",
    "autonomous",
)

# Workspace dropdown labels → runtime mode flags.
WORKSPACE_MODE_FLAGS: dict[str, str] = {
    "Chat Mode": "chat",
    "Autonomous Task": "autonomous",
    "Code Mode": "code",
    "Writing Mode": "writing",
    "Research Mode": "research",
    "Character Mode": "character",
    "Learn Mode": "learn",
}

_DEFAULT_MODE_LABELS: dict[str, str] = {
    flag: label for label, flag in WORKSPACE_MODE_FLAGS.items()
}


def workspace_label_for_default_mode(default_mode: str) -> str:
    """Map instance profile default_mode (short id or label) to workspace combo text."""
    raw = (default_mode or "chat").strip()
    if raw in WORKSPACE_MODE_FLAGS:
        return raw
    if raw in _DEFAULT_MODE_LABELS:
        return _DEFAULT_MODE_LABELS[raw]
    lower = raw.lower()
    for label, flag in WORKSPACE_MODE_FLAGS.items():
        if flag == lower or label.lower() == lower:
            return label
    return "Chat Mode"


def normalize_default_mode_id(default_mode: str) -> str:
    """Return short id for instance storage."""
    raw = (default_mode or "chat").strip()
    if raw in _DEFAULT_MODE_LABELS:
        return raw
    if raw in WORKSPACE_MODE_FLAGS:
        for label, flag in WORKSPACE_MODE_FLAGS.items():
            if label == raw:
                return flag
    lower = raw.lower()
    for label, flag in WORKSPACE_MODE_FLAGS.items():
        if flag == lower or label.lower() == lower:
            return flag
    return lower if lower in _DEFAULT_MODE_LABELS else "chat"
