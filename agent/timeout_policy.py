"""Adaptive Ollama read timeouts from estimated prompt size and context tier."""
from __future__ import annotations

import os

from context_budget import ContextProfile, ContextTier

_TIER_FLOOR: dict[ContextTier, int] = {
    "compact": 90,
    "standard": 100,
    "extended": 110,
    "max": 120,
}

_TIER_CAP_DEFAULT: dict[ContextTier, int] = {
    "compact": 180,
    "standard": 240,
    "extended": 300,
    "max": 600,
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _per_1k_seconds(tier: ContextTier) -> float:
    base = _env_int("AQUILA_TIMEOUT_PER_1K_TOKENS", 5)
    if tier == "max":
        return float(base)
    if tier == "extended":
        return float(max(3, base - 1))
    if tier == "standard":
        return float(max(2, base - 2))
    return float(max(1, base - 3))


def compute_read_timeout(
    *,
    estimated_prompt_tokens: int,
    profile: ContextProfile,
    stream: bool = False,
    explicit_timeout: int | None = None,
) -> int:
    """
    Scale read timeout with prompt size; 96k/max tier gets higher ceiling for unattended runs.
    """
    tier = profile.tier
    floor = _TIER_FLOOR.get(tier, 120)
    cap = _env_int("AQUILA_READ_TIMEOUT_MAX", _TIER_CAP_DEFAULT.get(tier, 300))

    est = max(0, estimated_prompt_tokens)
    scaled = floor + (est // 1000) * int(_per_1k_seconds(tier))
    if stream:
        scaled = max(scaled, floor)

    if explicit_timeout is not None and explicit_timeout > 0:
        scaled = max(scaled, explicit_timeout)

    return min(max(scaled, floor), cap)


def timeout_compress_retry_enabled(profile: ContextProfile) -> bool:
    raw = os.getenv("AQUILA_TIMEOUT_COMPRESS_RETRY", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return profile.tier == "max"


def is_system_error_response(raw: str) -> bool:
    text = (raw or "").strip()
    return text.startswith("*(API Error") or text.startswith("*(System")
