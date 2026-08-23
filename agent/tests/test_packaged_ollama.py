"""Packaged Ollama launcher tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import agent.remote.server_control as sc


def test_launch_mode_packaged(monkeypatch):
    monkeypatch.setattr(sc, "_launch_mode", lambda: "packaged")
    monkeypatch.setattr(sc, "probe", lambda url: False)
    monkeypatch.setattr(sc, "_get_tracked_pid", lambda e: None)
    monkeypatch.setattr(
        sc,
        "_packaged_ollama_binary",
        lambda: None,
    )
    result = sc.start_engine("stock")
    assert result["ok"] is False
    assert "bundled" in result["message"].lower()


@patch("agent.remote.server_control.subprocess.Popen")
def test_start_engine_packaged_spawns_ollama(mock_popen, monkeypatch, tmp_path):
    binary = tmp_path / "ollama.exe"
    binary.write_text("", encoding="utf-8")
    monkeypatch.setattr(sc, "_launch_mode", lambda: "packaged")
    monkeypatch.setattr(sc, "probe", lambda url: False)
    monkeypatch.setattr(sc, "_get_tracked_pid", lambda e: None)
    monkeypatch.setattr(sc, "_packaged_ollama_binary", lambda: binary)
    mock_proc = MagicMock()
    mock_proc.pid = 4242
    mock_popen.return_value = mock_proc
    monkeypatch.setattr(sc, "log_path", lambda e: tmp_path / "log.txt")
    result = sc._start_engine_packaged("stock")
    assert result["ok"] is True
    assert result["pid"] == 4242
    args = mock_popen.call_args[0][0]
    assert args[0] == str(binary)
    assert args[1] == "serve"
