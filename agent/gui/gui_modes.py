"""Shared mode identifiers for instance defaults (home) and workspace selector (gui)."""
from __future__ import annotations

import os

_DATA_LABEL = "Data Processing"
_DATA_ID = "data"

_BASE_INSTANCE_DEFAULT_MODE_IDS: tuple[str, ...] = (
    "chat",
    "research",
    "code",
    "writing",
    "character",
    "learn",
    "autonomous",
)

_BASE_WORKSPACE_MODE_FLAGS: dict[str, str] = {
    "Chat Mode": "chat",
    "Autonomous Task": "autonomous",
    "Code Mode": "code",
    "Writing Mode": "writing",
    "Research Mode": "research",
    "Character Mode": "character",
    "Learn Mode": "learn",
}


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def data_processing_enabled() -> bool:
    """Data Processing workspace is experimental; off unless AQUILA_ENABLE_DATA_PROCESSING=1."""
    return _env_bool("AQUILA_ENABLE_DATA_PROCESSING", default=False)


def build_instance_default_mode_ids() -> tuple[str, ...]:
    ids = list(_BASE_INSTANCE_DEFAULT_MODE_IDS)
    if data_processing_enabled():
        ids.append(_DATA_ID)
    return tuple(ids)


def build_workspace_mode_flags() -> dict[str, str]:
    flags = dict(_BASE_WORKSPACE_MODE_FLAGS)
    if data_processing_enabled():
        flags[_DATA_LABEL] = _DATA_ID
    return flags


# Computed at import (set env before importing gui in tests).
INSTANCE_DEFAULT_MODE_IDS = build_instance_default_mode_ids()
WORKSPACE_MODE_FLAGS = build_workspace_mode_flags()

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
    if lower == _DATA_ID and not data_processing_enabled():
        return "Chat Mode"
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
    if lower == _DATA_ID and not data_processing_enabled():
        return "chat"
    return lower if lower in _DEFAULT_MODE_LABELS else "chat"
