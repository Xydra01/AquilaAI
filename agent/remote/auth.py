"""Host ID + pairing + per-device token auth for the Remote Companion.

Security model (app layer, on top of Tailscale):

* On first use the host generates a stable ``host_id`` (uuid4) and a
  ``pairing_secret`` stored in ``remote_config.json``.
* To add a device you mint a short-lived 6-digit pairing code on the host and
  enter it (plus the Host ID) in the PWA once. The server checks the code and
  issues a long-lived random device token. Only a SHA-256 hash of the token is
  stored, so the config file can never re-create a token.
* Every API/WebSocket call presents ``Authorization: Bearer <token>`` (or a
  ``?token=`` query param for WebSockets). Lost devices are revoked by token id.

Because an open-source copy of the app ships with no secrets, nobody can pair
without a code generated on your machine.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import uuid
from typing import Optional

from . import config

_PAIR_CODE_TTL = 300.0  # 5 minutes


def _now() -> float:
    return time.time()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_code(code: str) -> str:
    """Salt the 6-digit code with the host's pairing secret before hashing.

    A bare SHA-256 of a 6-digit code is trivially brute-forced; salting with the
    private ``pairing_secret`` means a leaked config file cannot reveal codes.
    """
    secret = ensure_host_identity().get("pairing_secret", "")
    return hmac.new(secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def ensure_host_identity() -> dict:
    """Create host_id + pairing_secret on first run; return the full config."""
    cfg = config.load_config()
    changed = False
    if not cfg.get("host_id"):
        cfg["host_id"] = uuid.uuid4().hex
        changed = True
    if not cfg.get("pairing_secret"):
        cfg["pairing_secret"] = secrets.token_urlsafe(32)
        changed = True
    if changed:
        config.save_config(cfg)
    return cfg


def get_host_id() -> str:
    return ensure_host_identity()["host_id"]


# --- pairing codes ---------------------------------------------------------
#
# Codes are persisted to remote_config.json (not kept in process memory) so the
# `host_cli`/launcher process that *mints* a code and the uvicorn process that
# *verifies* it share the same store. Each entry is {"hash", "expires"}.

def _prune_pending(pending: list[dict]) -> list[dict]:
    now = _now()
    return [c for c in pending if float(c.get("expires", 0)) >= now]


def generate_pairing_code(ttl: float = _PAIR_CODE_TTL) -> str:
    """Mint a fresh 6-digit pairing code (shown on the host), persisted to config."""
    ensure_host_identity()
    code = f"{secrets.randbelow(1_000_000):06d}"
    cfg = config.load_config()
    pending = _prune_pending(cfg.get("pending_codes", []) or [])
    pending.append({"hash": _hash_code(code), "expires": _now() + ttl})
    cfg["pending_codes"] = pending
    config.save_config(cfg)
    return code


def verify_pairing_code(code: str, *, consume: bool = True) -> bool:
    code = (code or "").strip()
    if not code:
        return False
    code_hash = _hash_code(code)
    cfg = config.load_config()
    pending = _prune_pending(cfg.get("pending_codes", []) or [])
    match = next(
        (c for c in pending if hmac.compare_digest(c.get("hash", ""), code_hash)),
        None,
    )
    if match is None:
        # Persist any pruning of expired codes even on failure.
        if pending != (cfg.get("pending_codes") or []):
            cfg["pending_codes"] = pending
            config.save_config(cfg)
        return False
    if consume:
        cfg["pending_codes"] = [c for c in pending if c is not match]
        config.save_config(cfg)
    return True


# --- device tokens ---------------------------------------------------------

def pair_device(host_id: str, pairing_code: str, device_name: str = "device") -> Optional[dict]:
    """Validate Host ID + code, issue a device token.

    Returns ``{"token", "token_id", "name", "host_id"}`` on success, ``None`` on
    failure (wrong host id or bad/expired code).
    """
    cfg = ensure_host_identity()
    if not hmac.compare_digest(str(host_id or "").strip(), str(cfg["host_id"])):
        return None  # host id mismatch
    if not verify_pairing_code(pairing_code):
        return None

    token = secrets.token_urlsafe(32)
    token_id = uuid.uuid4().hex
    record = {
        "token_id": token_id,
        "name": (device_name or "device").strip()[:64] or "device",
        "token_hash": _hash_token(token),
        "created_at": _iso_now(),
        "last_seen_at": "",
    }
    cfg = config.load_config()
    cfg.setdefault("devices", []).append(record)
    config.save_config(cfg)
    return {
        "token": token,
        "token_id": token_id,
        "name": record["name"],
        "host_id": cfg["host_id"],
    }


def verify_token(token: str) -> Optional[dict]:
    """Return the device record for a valid token, else ``None``.

    Updates ``last_seen_at`` on success.
    """
    if auth_disabled():
        return {"token_id": "dev", "name": "no-auth", "created_at": "", "last_seen_at": ""}
    token = (token or "").strip()
    if not token:
        return None
    token_hash = _hash_token(token)
    cfg = config.load_config()
    for record in cfg.get("devices", []):
        stored = record.get("token_hash", "")
        if stored and hmac.compare_digest(stored, token_hash):
            record["last_seen_at"] = _iso_now()
            config.save_config(cfg)
            return {k: v for k, v in record.items() if k != "token_hash"}
    return None


def list_devices() -> list[dict]:
    cfg = config.load_config()
    return [
        {k: v for k, v in record.items() if k != "token_hash"}
        for record in cfg.get("devices", [])
    ]


def revoke_token(token_id: str) -> bool:
    cfg = config.load_config()
    devices = cfg.get("devices", [])
    remaining = [d for d in devices if d.get("token_id") != token_id]
    if len(remaining) == len(devices):
        return False
    cfg["devices"] = remaining
    config.save_config(cfg)
    return True


def auth_disabled() -> bool:
    """Allow turning off app-layer auth (e.g. trusted LAN/Tailscale-only dev)."""
    return os.getenv("AQUILA_REMOTE_NO_AUTH", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
