"""Tests for single-engine enforcement and captured engine logs."""
import pytest


@pytest.fixture(autouse=True)
def _data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    yield


def test_start_requires_confirm_when_other_running(monkeypatch):
    from remote import server_control

    # TQ is requested but Stock is already up → must ask for confirmation.
    def fake_probe(base_url):
        return base_url == server_control.ENGINES["stock"]["base_url"]

    monkeypatch.setattr(server_control, "probe", fake_probe)
    monkeypatch.setattr(server_control, "_get_tracked_pid", lambda e: None)

    result = server_control.start_engine("tq", stop_other=False)
    assert result["ok"] is False
    assert result["needs_confirm"] is True
    assert "Stock" in result["message"]


def test_start_stops_other_when_confirmed(monkeypatch):
    from remote import server_control

    state = {"stock_up": True, "stopped": []}

    def fake_probe(base_url):
        if base_url == server_control.ENGINES["stock"]["base_url"]:
            return state["stock_up"]
        return False

    class FakeProc:
        pid = 4242

    monkeypatch.setattr(server_control, "probe", fake_probe)
    monkeypatch.setattr(server_control, "_get_tracked_pid", lambda e: None)
    monkeypatch.setattr(server_control, "resolve_bash", lambda: "/bin/bash")
    monkeypatch.setattr(server_control, "_set_tracked_pid", lambda e, pid: None)

    def fake_stop(engine):
        state["stopped"].append(engine)
        state["stock_up"] = False
        return {"ok": True, "message": "stopped", "engine": engine}

    monkeypatch.setattr(server_control, "stop_engine", fake_stop)
    monkeypatch.setattr(server_control.subprocess, "Popen", lambda *a, **k: FakeProc())

    result = server_control.start_engine("tq", stop_other=True)
    assert result["ok"] is True
    assert "stock" in state["stopped"]
    assert result["pid"] == 4242


def test_tail_log_returns_recent_lines():
    from remote import server_control

    path = server_control.log_path("tq")
    path.write_text("\n".join(f"line {i}" for i in range(50)), encoding="utf-8")
    tail = server_control.tail_log("tq", lines=5)
    assert tail.splitlines() == ["line 45", "line 46", "line 47", "line 48", "line 49"]


def test_tail_log_unknown_engine_empty():
    from remote import server_control

    assert server_control.tail_log("bogus") == ""
