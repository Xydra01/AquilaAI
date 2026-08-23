"""Tests for packaged Ollama download/bundle helpers."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from agent.aquila_runtime import ollama_bundle as ob


def _fake_zip(path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ollama.exe", b"fake-ollama")
    path.write_bytes(buf.getvalue())


def test_ensure_packaged_ollama_uses_existing(tmp_path, monkeypatch):
    binary = tmp_path / "runtime" / "ollama" / "ollama.exe"
    binary.parent.mkdir(parents=True)
    binary.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ob, "is_frozen", lambda: True)
    monkeypatch.setattr(ob, "get_install_root", lambda: tmp_path)
    monkeypatch.setattr(
        ob,
        "packaged_ollama_binary",
        lambda: binary,
    )
    ok, msg = ob.ensure_packaged_ollama()
    assert ok is True
    assert "ollama.exe" in msg


def test_ensure_packaged_ollama_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "is_frozen", lambda: True)
    monkeypatch.setattr(ob, "get_install_root", lambda: tmp_path)
    monkeypatch.setattr(ob, "packaged_ollama_binary", lambda: None)
    monkeypatch.setattr(ob, "_host_arch", lambda: "amd64")

    def fake_download(url: str, dest: Path, on_progress) -> None:
        _fake_zip(dest)

    monkeypatch.setattr(ob, "_download", fake_download)

    ok, msg = ob.ensure_packaged_ollama()
    assert ok is True
    assert (tmp_path / "runtime" / "ollama" / "ollama.exe").is_file()
    assert "ollama.exe" in msg


def test_ensure_packaged_ollama_dev_without_binary(monkeypatch):
    monkeypatch.setattr(ob, "is_frozen", lambda: False)
    monkeypatch.setattr(ob, "packaged_ollama_binary", lambda: None)
    ok, msg = ob.ensure_packaged_ollama()
    assert ok is False
    assert "not found" in msg.lower()
