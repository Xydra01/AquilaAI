"""Tests for context_budget tier resolution."""
import os

import pytest

from context_budget import (
    get_context_profile,
    reset_runtime_context,
    resolve_context_profile,
    set_runtime_context,
)


@pytest.fixture(autouse=True)
def _reset_ctx():
    reset_runtime_context()
    yield
    reset_runtime_context()


def test_model_name_infers_96k():
    profile = resolve_context_profile("aquila-tq-96k")
    assert profile.num_ctx == 98304
    assert profile.tier == "max"
    assert profile.auto_scrape_urls == 3
    assert profile.scrape_char_cap == 40_000
    assert profile.max_scrape_chars_per_turn == 60_000


def test_model_name_infers_64k():
    profile = resolve_context_profile("aquila-tq-64k")
    assert profile.num_ctx == 65536
    assert profile.tier == "extended"
    assert profile.auto_scrape_urls == 2


def test_model_name_infers_32k():
    profile = resolve_context_profile("aquila-tq-32k")
    assert profile.num_ctx == 32768
    assert profile.tier == "standard"
    assert profile.auto_scrape_urls == 1


def test_num_ctx_override_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    profile = resolve_context_profile("aquila-tq-96k")
    assert profile.num_ctx == 8192
    assert profile.tier == "compact"


def test_forced_tier_env(monkeypatch):
    monkeypatch.setenv("AQUILA_CONTEXT_TIER", "max")
    profile = resolve_context_profile("aquila", num_ctx_override=4096)
    assert profile.tier == "max"
    assert profile.auto_scrape_urls == 3


def test_auto_scrape_disabled_env(monkeypatch):
    monkeypatch.setenv("AQUILA_AUTO_SCRAPE", "0")
    profile = resolve_context_profile("aquila-tq-64k")
    assert profile.auto_scrape_enabled is False


def test_set_runtime_context_cached():
    set_runtime_context("aquila-tq-64k", None)
    assert get_context_profile().tier == "extended"
