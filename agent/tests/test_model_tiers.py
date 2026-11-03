"""Tests for code mode model tier gating."""
from __future__ import annotations

import pytest

from agent.policies.model_tiers import (
    check_code_model,
    code_model_tier,
    normalize_model_tag,
)


def test_normalize_model_tag():
    assert normalize_model_tag("Aquila:latest") == "aquila"
    assert normalize_model_tag("aquila-qwopus-standard:latest") == "aquila-qwopus-standard"


def test_code_model_tier_capable():
    assert code_model_tier("aquila:latest") == "capable"
    assert code_model_tier("aquila") == "capable"


def test_code_model_tier_degraded():
    assert code_model_tier("aquila-qwopus-standard:latest") == "degraded"
    assert code_model_tier("aquila_qwopus") == "degraded"


def test_check_code_model_gui_blocks_degraded(monkeypatch):
    monkeypatch.delenv("AQUILA_CODE_ALLOW_DEGRADED_MODEL", raising=False)
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "1")
    result = check_code_model(surface="gui", model_id="aquila-qwopus-standard:latest")
    assert result.blocked is True
    assert result.ok is False
    assert "blocked" in result.message.lower() or "🛑" in result.message


def test_check_code_model_cli_warns_degraded(monkeypatch):
    monkeypatch.delenv("AQUILA_CODE_ALLOW_DEGRADED_MODEL", raising=False)
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "1")
    result = check_code_model(surface="cli", model_id="aquila-qwopus-standard:latest")
    assert result.ok is True
    assert result.warn is True


def test_check_code_model_cli_override(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_ALLOW_DEGRADED_MODEL", "1")
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "1")
    result = check_code_model(surface="cli", model_id="aquila-qwopus-standard:latest")
    assert result.ok is True
    assert result.blocked is False


def test_check_code_model_harness_strict(monkeypatch):
    monkeypatch.delenv("AQUILA_CODE_ALLOW_DEGRADED_MODEL", raising=False)
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "1")
    result = check_code_model(
        surface="harness",
        strict=True,
        model_id="aquila-qwopus-standard:latest",
    )
    assert result.ok is False
    assert result.blocked is True


def test_check_code_model_gate_disabled(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_MODEL_GATE", "0")
    result = check_code_model(surface="gui", model_id="aquila-qwopus-standard:latest")
    assert result.ok is True
    assert result.blocked is False
