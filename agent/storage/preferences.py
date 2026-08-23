"""Persisted Aquila preferences (catalog keys) in app_settings.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config_catalog import (
    catalog_defaults,
    catalog_settings,
    exportable_keys,
    validate_value,
)
from .env_parser import read_env, update_env
from .runtime_settings import _read_settings_blob, _settings_path
from .workspace_paths import get_data_root


def _env_file_path() -> Path:
    return get_data_root() / ".env"


def export_env_on_save() -> bool:
    blob = _read_settings_blob()
    if "export_env_on_save" not in blob:
        return True
    return bool(blob.get("export_env_on_save"))


def set_export_env_on_save(enabled: bool) -> Path:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_settings_blob()
    blob["export_env_on_save"] = bool(enabled)
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _saved_preferences_raw() -> dict[str, str]:
    blob = _read_settings_blob()
    raw = blob.get("preferences")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _migrate_from_env_if_needed() -> dict[str, str]:
    """One-time import from .env when preferences dict is empty."""
    saved = _saved_preferences_raw()
    if saved:
        return saved
    env_path = _env_file_path()
    if not env_path.is_file():
        return {}
    env_vals = read_env(env_path)
    catalog = catalog_settings()
    imported = {
        k: env_vals[k]
        for k in catalog
        if k in env_vals and env_vals[k] != ""
    }
    if not imported:
        return {}
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_settings_blob()
    blob["preferences"] = imported
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return imported


def load_preferences(*, env_override: bool = False) -> dict[str, str]:
    """Merge catalog defaults + saved preferences (+ optional .env overrides)."""
    merged = dict(catalog_defaults())
    merged.update(_migrate_from_env_if_needed())
    if env_override:
        env_path = _env_file_path()
        if env_path.is_file():
            for k, v in read_env(env_path).items():
                if k in merged and v != "":
                    merged[k] = v
    return merged


def save_preferences(
    updates: dict[str, str],
    *,
    export_env: bool | None = None,
) -> Path:
    """Validate and persist preference updates."""
    catalog = catalog_settings()
    current = load_preferences()
    for key, raw in updates.items():
        if key not in catalog:
            continue
        current[key] = validate_value(catalog[key], raw)

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_settings_blob()
    blob["preferences"] = current
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    do_export = export_env_on_save() if export_env is None else export_env
    if do_export:
        _export_preferences_to_env(current)
    apply_preferences_to_environ(current)
    return path


def _export_preferences_to_env(values: dict[str, str]) -> None:
    env_path = _env_file_path()
    if not env_path.is_file():
        env_path.write_text("", encoding="utf-8")
    export_keys = exportable_keys()
    updates = {k: v for k, v in values.items() if k in export_keys and v != ""}
    if updates:
        update_env(env_path, updates)


def apply_preferences_to_environ(values: dict[str, str] | None = None) -> None:
    """Hydrate os.environ from merged preferences (unset keys use catalog default)."""
    merged = values if values is not None else load_preferences()
    catalog = catalog_settings()
    for key, defn in catalog.items():
        val = merged.get(key, defn.default)
        if val == "" and defn.type != "str":
            os.environ.pop(key, None)
        else:
            os.environ[key] = val
