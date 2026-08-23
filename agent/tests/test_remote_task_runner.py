"""Tests for the job-style task runner (remote.tasks) and /api/task WebSocket."""
import asyncio

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402


def _collect(agen):
    async def run():
        out = []
        async for frame in agen:
            out.append(frame)
        return out

    return asyncio.run(run())


class FakeTaskAgent:
    def run_unified_task(self, task_name, prompt, mode, ui_callback=None, cancel_check=None, **kw):
        if ui_callback:
            ui_callback("step 1\n")
        return "# Deliverable\n\nDone."


def test_stream_task_emits_ledger_plan_done(monkeypatch):
    import main as brain
    from remote import session, tasks

    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)
    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeTaskAgent())
    monkeypatch.setattr(tasks, "_read_plan", lambda mode, name: {"steps": [{"title": "S1", "status": "done"}]})

    frames = _collect(
        tasks.stream_task(instance_id="i", task_name="t1", prompt="research X", mode="research")
    )
    types = [f["type"] for f in frames]
    assert "ledger" in types
    assert "plan" in types
    assert types[-1] == "done"
    done = frames[-1]
    assert "Deliverable" in done["message"]


def test_stream_task_busy_guard(monkeypatch):
    from remote import tasks, session

    class FakeLock:
        def locked(self):
            return True

    monkeypatch.setattr(session, "_chat_lock", FakeLock())

    frames = _collect(
        tasks.stream_task(instance_id="i", task_name="t", prompt="p", mode="research")
    )
    assert len(frames) == 1
    assert frames[0]["type"] == "busy"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import server

    with TestClient(server.app) as c:
        yield c


def _pair(client):
    from remote import auth

    return client.post(
        "/api/pair",
        json={"host_id": auth.get_host_id(), "pairing_code": auth.generate_pairing_code(), "device_name": "t"},
    ).json()["token"]


def test_task_websocket_streams_done(client, monkeypatch):
    import main as brain
    from remote import session, tasks

    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)
    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeTaskAgent())
    monkeypatch.setattr(tasks, "_read_plan", lambda mode, name: None)

    token = _pair(client)
    with client.websocket_connect(f"/api/task?token={token}") as ws:
        ws.send_json({"instance_id": "default", "prompt": "research X", "mode": "research"})
        frames = []
        while True:
            f = ws.receive_json()
            frames.append(f)
            if f["type"] in ("done", "error", "busy"):
                break
    assert frames[-1]["type"] == "done"
    assert "Deliverable" in frames[-1]["message"]


def test_task_websocket_rejects_empty_prompt(client):
    token = _pair(client)
    with client.websocket_connect(f"/api/task?token={token}") as ws:
        ws.send_json({"instance_id": "default", "prompt": "  "})
        frame = ws.receive_json()
    assert frame["type"] == "error"


def test_deliverable_listing_endpoint(client, tmp_path, monkeypatch):
    from agent.storage import agent_data_path

    research_dir = agent_data_path("Agent-Research")
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "report.md").write_text("# Hello", encoding="utf-8")

    token = _pair(client)
    h = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/research/deliverables", headers=h)
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["deliverables"]]
    assert "report.md" in names

    path = resp.json()["deliverables"][0]["path"]
    doc = client.get(f"/api/deliverable?path={path}", headers=h)
    assert doc.status_code == 200
    assert "Hello" in doc.json()["text"]


def test_deliverable_path_traversal_blocked(client, monkeypatch):
    token = _pair(client)
    h = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/deliverable?path=/etc/passwd", headers=h)
    assert resp.status_code == 404
