"""Tests for Remote Companion server_control (start/stop/status, bash resolution)."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sc(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import server_control

    return server_control


def test_status_all_down(sc):
    with patch.object(sc, "probe", return_value=False):
        engines = sc.engine_status()
    names = {e["engine"] for e in engines}
    assert names == {"tq", "stock"}
    for e in engines:
        assert e["up"] is False
        assert e["managed_pid"] is None
        assert e["loaded_models"] == []


def test_start_engine_launches_bash_with_sh_script(sc):
    fake = MagicMock()
    fake.pid = 4242
    with patch.object(sc, "probe", return_value=False), patch.object(
        sc, "resolve_bash", return_value="/usr/bin/bash"
    ), patch("subprocess.Popen", return_value=fake) as popen:
        result = sc.start_engine("tq")

    assert result["ok"] is True
    assert result["pid"] == 4242
    assert sc._get_tracked_pid("tq") == 4242
    argv = popen.call_args[0][0]
    assert argv[0] == "/usr/bin/bash"
    assert argv[1].endswith("ollama-serve-turboquant-port.sh")


def test_start_engine_already_running(sc):
    with patch.object(sc, "probe", return_value=True):
        result = sc.start_engine("stock")
    assert result["ok"] is True
    assert "already" in result["message"].lower()


def test_start_engine_no_bash(sc):
    with patch.object(sc, "probe", return_value=False), patch.object(
        sc, "resolve_bash", return_value=None
    ):
        result = sc.start_engine("tq")
    assert result["ok"] is False
    assert "bash" in result["message"].lower()


def test_stop_engine_without_tracked_pid(sc):
    result = sc.stop_engine("tq")
    assert result["ok"] is False
    assert "no managed" in result["message"].lower()


def test_stop_engine_terminates_and_clears(sc):
    sc._set_tracked_pid("stock", 9999)
    with patch.object(sc, "_terminate_tree", return_value=True) as term:
        result = sc.stop_engine("stock")
    term.assert_called_once_with(9999)
    assert result["ok"] is True
    assert sc._get_tracked_pid("stock") is None


def test_unknown_engine(sc):
    assert sc.start_engine("bogus")["ok"] is False
    assert sc.stop_engine("bogus")["ok"] is False


def test_resolve_bash_env_override(sc, tmp_path, monkeypatch):
    fake_bash = tmp_path / "mybash"
    fake_bash.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("AQUILA_BASH_BIN", str(fake_bash))
    assert sc.resolve_bash() == str(fake_bash)


def test_status_clears_dead_pid(sc):
    sc._set_tracked_pid("tq", 123456)
    with patch.object(sc, "probe", return_value=False), patch.object(
        sc, "_pid_alive", return_value=False
    ):
        engines = sc.engine_status()
    tq = next(e for e in engines if e["engine"] == "tq")
    assert tq["managed_pid"] is None
    assert sc._get_tracked_pid("tq") is None
