"""Tests for Remote Companion auth + config (Host ID, pairing, device tokens)."""
import json

import pytest


@pytest.fixture
def remote_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AQUILA_REMOTE_NO_AUTH", raising=False)
    from remote import auth, config

    return auth, config


def test_host_identity_is_stable_and_persisted(remote_auth, tmp_path):
    auth, config = remote_auth
    hid1 = auth.get_host_id()
    hid2 = auth.get_host_id()
    assert hid1 == hid2 and len(hid1) == 32

    cfg_file = tmp_path / "Agent-Instances" / "remote_config.json"
    assert cfg_file.is_file()
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["host_id"] == hid1
    assert data["pairing_secret"]


def test_pairing_code_is_one_time(remote_auth):
    auth, _ = remote_auth
    code = auth.generate_pairing_code()
    assert len(code) == 6 and code.isdigit()
    assert auth.verify_pairing_code(code) is True
    # consumed
    assert auth.verify_pairing_code(code) is False


def test_pairing_code_persisted_to_config_for_cross_process(remote_auth, tmp_path):
    """A code minted by one process (e.g. the launcher CLI) must be verifiable by
    the separate uvicorn process. Both share remote_config.json on disk."""
    auth, config = remote_auth
    code = auth.generate_pairing_code()

    # Persisted (hashed, not plaintext) so another process can read it.
    cfg_file = tmp_path / "Agent-Instances" / "remote_config.json"
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert len(data["pending_codes"]) == 1
    assert data["pending_codes"][0]["hash"] != code  # stored as a salted hash

    # A fresh read of config (stand-in for the other process) still verifies it.
    assert auth.verify_pairing_code(code) is True
    # consumed -> removed from the shared store
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["pending_codes"] == []


def test_pair_device_success_then_verify(remote_auth):
    auth, _ = remote_auth
    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    result = auth.pair_device(hid, code, "phone")
    assert result is not None
    assert result["token"] and result["name"] == "phone"

    device = auth.verify_token(result["token"])
    assert device is not None
    assert device["name"] == "phone"
    assert "token_hash" not in device  # never leak the hash


def test_pair_device_rejects_bad_host_or_code(remote_auth):
    auth, _ = remote_auth
    hid = auth.get_host_id()
    code = auth.generate_pairing_code()
    assert auth.pair_device("not-the-host", code, "x") is None
    # a wrong code never matches
    assert auth.pair_device(hid, "000000", "x") is None


def test_verify_token_rejects_unknown(remote_auth):
    auth, _ = remote_auth
    assert auth.verify_token("definitely-not-a-token") is None
    assert auth.verify_token("") is None


def test_revoke_token(remote_auth):
    auth, _ = remote_auth
    hid = auth.get_host_id()
    result = auth.pair_device(hid, auth.generate_pairing_code(), "laptop")
    token = result["token"]
    devices = auth.list_devices()
    assert len(devices) == 1
    token_id = devices[0]["token_id"]

    assert auth.revoke_token(token_id) is True
    assert auth.verify_token(token) is None
    assert auth.revoke_token(token_id) is False  # already gone


def test_auth_disabled_env_bypass(remote_auth, monkeypatch):
    auth, _ = remote_auth
    monkeypatch.setenv("AQUILA_REMOTE_NO_AUTH", "1")
    device = auth.verify_token("")
    assert device is not None and device["name"] == "no-auth"
