"""Tests for harness gate runner."""
from __future__ import annotations

from unittest.mock import patch

from agent.core.harness_gate import run_gate


def test_run_gate_fails_on_engine_unreachable(monkeypatch):
    monkeypatch.setattr(
        "agent.core.harness_gate.configure_engine",
        lambda eng: (False, "unreachable"),
    )
    out = run_gate(engine="stock")
    assert out["ok"] is False
    assert "unreachable" in out.get("error", "")


def test_run_gate_fails_on_degraded_model_strict(monkeypatch):
    monkeypatch.setattr(
        "agent.core.harness_gate.configure_engine",
        lambda eng: (True, "http://127.0.0.1:11434"),
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.get_active_model_id",
        lambda: "aquila-qwopus-standard:latest",
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.code_model_tier",
        lambda _mid=None: "degraded",
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.check_code_model",
        lambda **kwargs: type(
            "R",
            (),
            {"ok": False, "blocked": True, "message": "degraded", "warn": False},
        )(),
    )
    out = run_gate(engine="stock", allow_degraded=False)
    assert out["ok"] is False


@patch("agent.core.harness_gate.run_and_evaluate")
def test_run_gate_passes_when_scenarios_pass(mock_run, monkeypatch):
    monkeypatch.setattr(
        "agent.core.harness_gate.configure_engine",
        lambda eng: (True, "http://127.0.0.1:11434"),
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.get_active_model_id",
        lambda: "aquila:latest",
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.code_model_tier",
        lambda _mid=None: "capable",
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.check_code_model",
        lambda **kwargs: type(
            "R",
            (),
            {"ok": True, "blocked": False, "message": "", "warn": False},
        )(),
    )
    mock_run.return_value = (True, {"passed": True, "failures": [], "task_name": "t1"})

    out = run_gate(engine="stock", runs=1)
    assert out["ok"] is True
    assert mock_run.call_count == 2


@patch("agent.core.harness_gate.run_and_evaluate")
def test_run_gate_fails_when_scenario_fails(mock_run, monkeypatch):
    monkeypatch.setattr(
        "agent.core.harness_gate.configure_engine",
        lambda eng: (True, "http://127.0.0.1:11434"),
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.get_active_model_id",
        lambda: "aquila:latest",
    )
    monkeypatch.setattr(
        "agent.core.harness_gate.check_code_model",
        lambda **kwargs: type(
            "R",
            (),
            {"ok": True, "blocked": False, "message": "", "warn": False},
        )(),
    )
    mock_run.return_value = (False, {"passed": False, "failures": ["scorecard: fail"]})

    out = run_gate(engine="stock", runs=1)
    assert out["ok"] is False
    assert out["failures"]
