"""Tests for the Remote Companion uploads cache + /api/uploads endpoint."""
from unittest.mock import patch

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import server, uploads

    uploads.clear()
    with TestClient(server.app) as c:
        yield c


def _pair(client):
    from remote import auth

    return client.post(
        "/api/pair",
        json={"host_id": auth.get_host_id(), "pairing_code": auth.generate_pairing_code(), "device_name": "t"},
    ).json()["token"]


def test_store_and_resolve_tokens(monkeypatch):
    from remote import uploads

    uploads.clear()
    with patch("file_parser.process_local_attachments", return_value=(["chunk text"], ["imgb64"])):
        result = uploads.store_files([("notes.txt", b"hello")])
    assert result["upload_token"]
    assert result["file_names"] == ["notes.txt"]
    assert result["has_images"] is True

    chunks, images = uploads.resolve_tokens([result["upload_token"]])
    assert chunks == ["chunk text"]
    assert images == ["imgb64"]


def test_unknown_token_is_ignored():
    from remote import uploads

    chunks, images = uploads.resolve_tokens(["nope"])
    assert chunks == [] and images == []


def test_upload_endpoint_returns_token(client):
    token = _pair(client)
    with patch("file_parser.process_local_attachments", return_value=(["parsed"], [])):
        resp = client.post(
            "/api/uploads",
            headers={"Authorization": f"Bearer {token}"},
            files=[("files", ("a.txt", b"data", "text/plain"))],
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_token"]
    assert body["file_names"] == ["a.txt"]
    assert body["has_images"] is False


def test_upload_requires_auth(client):
    resp = client.post("/api/uploads", files=[("files", ("a.txt", b"x", "text/plain"))])
    assert resp.status_code == 401
