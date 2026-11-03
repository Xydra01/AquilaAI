"""Live habit-tracker harness (requires Ollama)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

pytestmark = pytest.mark.live


def _stock_reachable() -> bool:
    try:
        import requests

        return requests.get("http://127.0.0.1:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _stock_reachable(), reason="stock Ollama not reachable")
def test_live_code_habit_tracker_stock():
    from agent.core.capability_harness import evaluate_run, run_scenario
    from agent.core.code_run_diagnostics import diagnose_code_run, format_diagnostic_report

    rep = run_scenario("code_habit_tracker", engine="stock")
    assert rep.get("ok") is True, rep
    task = rep.get("task_name") or ""
    diag = diagnose_code_run(task)
    print(format_diagnostic_report(diag))
    passed, failures = evaluate_run(rep)
    assert passed, failures
