"""Remote API tests for runtime settings and search endpoints."""
import os
import sys
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import server

    with TestClient(server.app) as c:
        yield c


def _auth_headers(client):
    from remote import auth

    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    resp = client.post(
        "/api/pair",
        json={"host_id": hid, "pairing_code": code, "device_name": "tester"},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_runtime_settings_get_put(client):
    headers = _auth_headers(client)
    resp = client.get("/api/runtime/settings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "ollama_base_url" in data

    resp2 = client.put(
        "/api/runtime/settings",
        headers=headers,
        json={"ollama_model": "aquila_heretic", "searxng_engines": "duckduckgo"},
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["ollama_model"] == "aquila_heretic"
    assert body["searxng_engines"] == "duckduckgo"


def test_ollama_models_endpoint(client):
    headers = _auth_headers(client)
    with patch("main.client.list_models", return_value=["aquila_heretic:latest"]):
        resp = client.get("/api/ollama/models?engine=stock", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["models"] == ["aquila_heretic:latest"]


def test_search_status_endpoint(client):
    headers = _auth_headers(client)
    with patch("agent.research.probe_health", return_value=(True, "ok")), patch(
        "agent.research.docker_status",
        return_value={"available": True, "running": False},
    ):
        resp = client.get("/api/search/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
