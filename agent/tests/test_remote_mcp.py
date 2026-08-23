"""Remote MCP server configuration API."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AQUILA_REMOTE_NO_AUTH", raising=False)
    from remote import server

    with TestClient(server.app) as c:
        yield c


def _auth_headers(client):
    from remote import auth

    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    resp = client.post(
        "/api/pair",
        json={"host_id": hid, "pairing_code": code, "device_name": "mcp-tester"},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_mcp_servers_api_get(client):
    headers = _auth_headers(client)
    r = client.get("/api/mcp/servers", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "servers" in data
    assert "health" in data


def test_mcp_servers_api_put(client):
    headers = _auth_headers(client)
    payload = {
        "servers": [
            {
                "name": "test-stub",
                "transport": "stdio",
                "command": "",
                "enabled": False,
            }
        ]
    }
    r = client.put("/api/mcp/servers", json=payload, headers=headers)
    assert r.status_code == 200
    assert r.json()["servers"][0]["name"] == "test-stub"
