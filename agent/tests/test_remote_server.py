"""Tests for the Remote Companion FastAPI app (pairing, chat WS, server endpoints)."""
from unittest.mock import patch

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AQUILA_REMOTE_NO_AUTH", raising=False)
    from remote import server

    with TestClient(server.app) as c:
        yield c


def _pair(client):
    from remote import auth

    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    resp = client.post(
        "/api/pair",
        json={"host_id": hid, "pairing_code": code, "device_name": "tester"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def test_health_reports_host_id(client):
    data = client.get("/api/health").json()
    assert data["ok"] is True
    assert len(data["host_id"]) == 32


def test_pairing_rejects_bad_code(client):
    from remote import auth

    hid = auth.get_host_id()
    resp = client.post(
        "/api/pair", json={"host_id": hid, "pairing_code": "000000", "device_name": "x"}
    )
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/instances").status_code == 401
    token = _pair(client)
    resp = client.get("/api/instances", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "instances" in resp.json()


def test_chat_websocket_streams_mocked_agent(client, monkeypatch):
    import main as brain
    from remote import session

    class FakeAgent:
        def run_chat(self, message, history, image_payloads=None, text_chunks=None, stream=True):
            yield {"message": {"thinking": "let me think"}}
            yield {"message": {"content": "Hello "}}
            yield {"message": {"content": "world"}}

    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeAgent())
    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)

    token = _pair(client)
    with client.websocket_connect(f"/api/chat?token={token}") as ws:
        ws.send_json({"instance_id": "default", "message": "hi", "history": []})
        frames = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame["type"] in ("done", "error"):
                break

    types = [f["type"] for f in frames]
    assert "thinking" in types
    assert "token" in types
    done = frames[-1]
    assert done["type"] == "done"
    assert done["content"] == "Hello world"


def test_chat_websocket_thread_id_persists_server_history(client, monkeypatch):
    import main as brain
    from remote import session

    class FakeAgent:
        def run_chat(self, message, history, image_payloads=None, text_chunks=None, stream=True):
            assert history and history[-1]["content"] == "prior answer"
            yield {"message": {"content": "new answer"}}

    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeAgent())
    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)
    from agent.storage import create_thread, save_thread_history, load_thread_history

    t = create_thread("default", "Server thread test")
    save_thread_history("default", t.id, [
        {"role": "user", "content": "prior question"},
        {"role": "assistant", "content": "prior answer"},
    ])

    token = _pair(client)
    with client.websocket_connect(f"/api/chat?token={token}") as ws:
        ws.send_json({
            "instance_id": "default",
            "message": "next question",
            "history": [],
            "thread_id": t.id,
        })
        while True:
            frame = ws.receive_json()
            if frame["type"] in ("done", "error"):
                break

    hist = load_thread_history("default", t.id)
    assert hist[-2]["content"] == "next question"
    assert hist[-1]["content"] == "new answer"


def test_chat_websocket_accepts_bounded_tools_flag(client, monkeypatch):
    import main as brain
    from remote import session

    class FakeAgent:
        def run_bounded_tools_chat(self, user_input, chat_history, **kw):
            yield {"message": {"content": "ok"}}

    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeAgent())
    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)

    token = _pair(client)
    with client.websocket_connect(f"/api/chat?token={token}") as ws:
        ws.send_json({"instance_id": "default", "message": "hi", "history": [], "bounded_tools": True})
        while True:
            frame = ws.receive_json()
            if frame["type"] in ("done", "error"):
                assert frame["type"] == "done"
                break


def test_chat_websocket_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/chat?token=nope") as ws:
            ws.receive_json()


def test_server_status_endpoint(client, monkeypatch):
    from remote import server_control

    fake = [
        {"engine": "tq", "base_url": "http://127.0.0.1:11435", "up": False, "managed_pid": None, "loaded_models": []},
        {"engine": "stock", "base_url": "http://127.0.0.1:11434", "up": True, "managed_pid": 5, "loaded_models": ["aquila"]},
    ]
    monkeypatch.setattr(server_control, "engine_status", lambda: fake)
    token = _pair(client)
    resp = client.get("/api/server/status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["engines"] == fake


def test_server_start_stop_endpoints(client, monkeypatch):
    from remote import server_control

    monkeypatch.setattr(
        server_control,
        "start_engine",
        lambda engine, stop_other=False: {"ok": True, "message": "starting", "engine": engine, "pid": 11},
    )
    monkeypatch.setattr(
        server_control,
        "stop_engine",
        lambda engine: {"ok": True, "message": "stopped", "engine": engine},
    )
    token = _pair(client)
    h = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/server/start", json={"engine": "tq"}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["pid"] == 11

    r = client.post("/api/server/stop", json={"engine": "tq"}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True


def test_model_warmup_eject_endpoints(client, monkeypatch):
    from remote import server_control

    monkeypatch.setattr(server_control, "warmup_model", lambda base_url=None: {"ok": True, "message": "ready"})
    monkeypatch.setattr(
        server_control, "eject_model", lambda base_url=None, all_loaded=False: {"ok": True, "message": "ejected"}
    )
    token = _pair(client)
    h = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/model/warmup", json={"model": "tq"}, headers=h)
    assert r.status_code == 200 and r.json()["message"] == "ready"

    r = client.post("/api/model/eject", json={"model": "stock", "all_loaded": True}, headers=h)
    assert r.status_code == 200 and r.json()["message"] == "ejected"


def test_chat_thread_regenerate_and_edit_endpoints(client):
    from agent.storage import create_thread, save_thread_history

    token = _pair(client)
    h = {"Authorization": f"Bearer {token}"}
    t = create_thread("default", "Remote thread")
    save_thread_history(
        "default",
        t.id,
        [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ],
    )
    r = client.post(
        f"/api/chat/threads/{t.id}/regenerate",
        json={"instance_id": "default"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["prompt"] == "u1"

    r = client.post(
        f"/api/chat/threads/{t.id}/edit-last",
        json={"instance_id": "default", "text": "u1-edited"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["history"][-1]["content"] == "u1-edited"
