import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import reset_runtime_context, resolve_context_profile


@pytest.fixture(autouse=True)
def _reset_ctx(monkeypatch):
    monkeypatch.delenv("AQUILA_CONTEXT_TIER", raising=False)
    reset_runtime_context()
    yield
    reset_runtime_context()


def test_turboquant_model_defaults_to_extended_tier(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "aquila-tq-64k")
    profile = resolve_context_profile("aquila-tq-64k")
    assert profile.tier == "extended"
    assert profile.max_scrape_chars_per_turn > 0


def test_explicit_tier_overrides_turboquant_default(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "aquila-tq-64k")
    monkeypatch.setenv("AQUILA_CONTEXT_TIER", "compact")
    profile = resolve_context_profile("aquila-tq-64k")
    assert profile.tier == "compact"
