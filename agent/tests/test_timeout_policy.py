"""Adaptive read timeout policy."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from context_budget import resolve_context_profile
from timeout_policy import (
    _TIER_CAP_DEFAULT,
    compute_read_timeout,
    timeout_compress_retry_enabled,
)


def test_max_tier_scales_with_tokens(monkeypatch):
    monkeypatch.delenv("AQUILA_READ_TIMEOUT_MAX", raising=False)
    profile = resolve_context_profile("aquila-tq-96k")
    small = compute_read_timeout(estimated_prompt_tokens=1000, profile=profile)
    large = compute_read_timeout(estimated_prompt_tokens=40_000, profile=profile)
    assert large > small
    assert large >= 120


def test_max_tier_respects_cap(monkeypatch):
    monkeypatch.setenv("AQUILA_READ_TIMEOUT_MAX", "200")
    profile = resolve_context_profile("aquila-tq-96k")
    t = compute_read_timeout(estimated_prompt_tokens=100_000, profile=profile)
    assert t <= 200


def test_compact_tier_bounded(monkeypatch):
    monkeypatch.setenv("AQUILA_READ_TIMEOUT_MAX", "600")
    monkeypatch.setenv("AQUILA_CONTEXT_TIER", "compact")
    profile = resolve_context_profile("aquila", num_ctx_override=8192)
    t = compute_read_timeout(estimated_prompt_tokens=50_000, profile=profile)
    assert t <= _TIER_CAP_DEFAULT["compact"] + 20


def test_compress_retry_default_on_max():
    profile = resolve_context_profile("aquila-tq-96k")
    assert timeout_compress_retry_enabled(profile) is True
