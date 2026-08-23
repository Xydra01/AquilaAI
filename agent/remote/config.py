"""Persistent config for the Remote Companion: Host ID, pairing secret, devices.

Stored at ``Agent-Instances/remote_config.json`` (under the canonical data root,
so it honors ``AQUILA_DATA_ROOT`` in tests). Access is guarded by a process lock
because the API can touch it from multiple request handlers.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "remote_config.json"
_lock = threading.RLock()


def _config_path() -> Path:
    from agent.storage import agent_data_path

    base = agent_data_path("Agent-Instances")
    base.mkdir(parents=True, exist_ok=True)
    return base / CONFIG_FILENAME


def _default_config() -> dict[str, Any]:
    return {
        "host_id": "",
        "pairing_secret": "",
        "devices": [],
        "servers": {},
        "pending_codes": [],
    }


def load_config() -> dict[str, Any]:
    with _lock:
        path = _config_path()
        if not path.is_file():
            return _default_config()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _default_config()
        if not isinstance(data, dict):
            return _default_config()
        base = _default_config()
        base.update(data)
        base.setdefault("devices", [])
        base.setdefault("servers", {})
        base.setdefault("pending_codes", [])
        return base


def save_config(config: dict[str, Any]) -> None:
    with _lock:
        path = _config_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
        tmp.replace(path)


def update_config(**changes: Any) -> dict[str, Any]:
    with _lock:
        config = load_config()
        config.update(changes)
        save_config(config)
        return config
