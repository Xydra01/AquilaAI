"""Tests for packaged SearXNG support files."""
from __future__ import annotations

from pathlib import Path

from agent.aquila_runtime import search_bundle as sb


def test_ensure_search_support_files_copies_from_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docker-compose.yml").write_text("services:\n", encoding="utf-8")
    (repo / "searxng-settings.yml").write_text("use_default_settings: true\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()

    monkeypatch.setattr(sb, "search_support_dir", lambda: data)
    monkeypatch.setattr(sb, "get_bundled_path", lambda *parts: repo.joinpath(*parts))
    monkeypatch.setattr(sb, "REPO_ROOT", repo)

    ok, msg = sb.ensure_search_support_files()
    assert ok is True
    assert (data / "docker-compose.yml").is_file()
    assert (data / "searxng-settings.yml").is_file()
    assert "docker-compose.yml" in msg or msg.endswith("docker-compose.yml")


def test_ensure_search_support_files_no_source(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(sb, "search_support_dir", lambda: data)
    monkeypatch.setattr(sb, "get_bundled_path", lambda *parts: Path("missing"))
    monkeypatch.setattr(sb, "REPO_ROOT", tmp_path / "norepo")

    ok, msg = sb.ensure_search_support_files()
    assert ok is False
    assert "optional" in msg.lower()
