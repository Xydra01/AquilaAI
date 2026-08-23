"""Tests for config_catalog completeness and helpers."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent.storage.config_catalog import (
    INTERNAL_KEYS,
    catalog_defaults,
    catalog_settings,
    load_catalog,
    validate_value,
    write_env_example,
)


def _discover_aquila_keys(repo_root: Path) -> set[str]:
    pattern = re.compile(r'os\.getenv\(\s*["\'](AQUILA_[A-Z0-9_]+)["\']')
    keys: set[str] = set()
    agent_dir = repo_root / "agent"
    for path in agent_dir.rglob("*.py"):
        if "config_catalog.py" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        keys.update(pattern.findall(text))
    return keys


def test_catalog_has_all_runtime_aquila_keys():
    repo = Path(__file__).resolve().parents[2]
    discovered = _discover_aquila_keys(repo)
    catalog = set(catalog_settings())
    missing = discovered - catalog - INTERNAL_KEYS
    assert not missing, f"AQUILA_* keys missing from catalog: {sorted(missing)}"


def test_catalog_defaults_match_types():
    for key, defn in catalog_settings().items():
        if defn.default == "" and defn.type != "str":
            continue
        validate_value(defn, defn.default)


def test_chat_light_research_section_exists():
    sections = {s.id: s for s in load_catalog()}
    assert "chat_light_research" in sections
    keys = {s.key for s in sections["chat_light_research"].settings}
    assert "AQUILA_LIGHT_RESEARCH_MAX_USER_URLS" in keys
    assert "AQUILA_LIGHT_RESEARCH_USER_URL_READS" in keys


def test_write_env_example(tmp_path, monkeypatch):
    target = tmp_path / ".env.EXAMPLE"
    monkeypatch.setattr(
        "agent.storage.config_catalog.REPO_ROOT",
        tmp_path,
    )
    write_env_example(target)
    text = target.read_text(encoding="utf-8")
    assert "AQUILA_LIGHT_RESEARCH_MAX_USER_URLS" in text
    assert "AQUILA_LIGHT_RESEARCH_USER_URL_READS" in text


def test_catalog_defaults_includes_new_url_key():
    defaults = catalog_defaults()
    assert defaults["AQUILA_LIGHT_RESEARCH_MAX_USER_URLS"] == "3"
