import json
import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_finish_task_ends_run(tmp_agent_dirs, write_ledger, monkeypatch):
    import main as main_mod

    write_ledger(
        "Agent-Tasks/finish_me.json",
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{"description": "Final", "max_iterations": 3}],
        },
    )

    suffix = (
        'Done.", "tools": [{"name": "finish_task", '
        '"arguments": {"message_to_user": "All done!"}}]}'
    )

    def fake_chat(*args, **kwargs):
        return {"message": {"content": suffix}}

    monkeypatch.setattr(main_mod.client, "chat", fake_chat)
    monkeypatch.setattr(
        main_mod.aquila_memory,
        "store_experience",
        lambda *a, **k: None,
    )
    agent = main_mod.Agent()
    result = agent.run_unified_task("finish_me", "goal", mode="autonomous")
    assert "All done!" in result


def test_cancel_check_aborts(tmp_agent_dirs, write_ledger, monkeypatch):
    import main as main_mod

    write_ledger(
        "Agent-Tasks/cancel_me.json",
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{"description": "Work", "max_iterations": 5}],
        },
    )

    agent = main_mod.Agent()
    result = agent.run_unified_task(
        "cancel_me",
        "goal",
        mode="autonomous",
        cancel_check=lambda: True,
    )
    assert "aborted" in result.lower()


def test_mark_objective_complete_advances(tmp_agent_dirs, write_ledger, monkeypatch):
    import main as main_mod

    ledger_path = write_ledger(
        "Agent-Tasks/advance_me.json",
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [
                {"description": "Step A", "max_iterations": 3},
                {"description": "Step B", "max_iterations": 3},
            ],
        },
    )

    responses = [
        (
            'Step A.", "tools": [{"name": "mark_objective_complete", '
            '"arguments": {"summary_of_work": "A done"}}]}'
        ),
        (
            'Done.", "tools": [{"name": "finish_task", '
            '"arguments": {"message_to_user": "Done"}}]}'
        ),
    ]
    idx = {"i": 0}

    def fake_chat(*args, **kwargs):
        payload = responses[min(idx["i"], len(responses) - 1)]
        idx["i"] += 1
        return {"message": {"content": payload}}

    monkeypatch.setattr(main_mod.client, "chat", fake_chat)
    monkeypatch.setattr(main_mod.aquila_memory, "store_experience", lambda *a, **k: None)
    agent = main_mod.Agent()
    agent.run_unified_task("advance_me", "goal", mode="autonomous")

    state = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert state["current_step_index"] >= 1 or state["status"] == "completed"
