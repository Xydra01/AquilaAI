"""Remote Companion Aquila MCP host SSE mount."""
import asyncio

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AQUILA_REMOTE_NO_AUTH", raising=False)
    from remote import mcp_host_mount

    mcp_host_mount._mcp_sse_app = None
    from remote import server

    with TestClient(server.app) as c:
        yield c


def _pair(client):
    from remote import auth

    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    resp = client.post(
        "/api/pair",
        json={"host_id": hid, "pairing_code": code, "device_name": "mcp-host-tester"},
    )
    return resp.json()["token"]


def test_mcp_host_sse_requires_auth(client):
    resp = client.get("/api/mcp/host/sse")
    assert resp.status_code == 401


def test_mcp_host_auth_middleware_accepts_token(tmp_path, monkeypatch):
    """Auth middleware should pass valid tokens without opening a long-lived SSE stream."""
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import auth
    from remote.mcp_host_mount import McpHostAuthMiddleware

    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    token = auth.pair_device(hid, code, "mcp-host-tester")["token"]

    reached = []

    async def inner(scope, receive, send):
        reached.append(True)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = McpHostAuthMiddleware(inner)
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def capture_send(msg):
        sent.append(msg)

    async def run():
        await middleware(scope, receive, capture_send)

    asyncio.run(run())
    assert reached == [True]
    assert sent and sent[0]["status"] == 204


def test_mcp_host_auth_middleware_accepts_query_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import auth
    from remote.mcp_host_mount import McpHostAuthMiddleware

    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    token = auth.pair_device(hid, code, "mcp-host-tester")["token"]

    reached = []

    async def inner(scope, receive, send):
        reached.append(True)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = McpHostAuthMiddleware(inner)
    scope = {
        "type": "http",
        "headers": [],
        "query_string": f"token={token}".encode(),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def capture_send(msg):
        sent.append(msg)

    asyncio.run(middleware(scope, receive, capture_send))
    assert reached == [True]
    assert sent and sent[0]["status"] == 204
