import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    complete_ledger_state,
    save_task_deliverable,
    read_json_state,
    initialize_json_ledger,
)


def test_complete_ledger_state_marks_all_steps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Agent-Tasks").mkdir()
    task_file = tmp_path / "Agent-Tasks" / "done_task.json"
    initialize_json_ledger(str(task_file), ["Step A", "Step B"])

    complete_ledger_state(str(task_file), "All done.")

    state = read_json_state(str(task_file))
    assert state["status"] == "completed"
    assert state["current_step_index"] == 2
    assert all(s["status"] == "completed" for s in state["steps"])


def test_save_task_deliverable_research(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = save_task_deliverable("my_research", "research", "# Report\n\nBody")
    assert path is not None
    assert os.path.exists(path)
    assert "Agent-Research" in path.replace("\\", "/")
    with open(path, encoding="utf-8") as f:
        assert "Report" in f.read()


def test_finish_task_saves_report_from_arguments(tmp_agent_dirs, write_ledger, monkeypatch):
    import main as main_mod

    write_ledger(
        "Agent-Plans/research_task.json",
        {
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{"description": "Research", "max_iterations": 2}],
        },
    )

    suffix = (
        'Done.", "final_report": "# My Report\\n\\nFindings here.", '
        '"tools": [{"name": "finish_task", "arguments": {"message_to_user": "Done"}}]}'
    )

    def fake_chat(*args, **kwargs):
        return {"message": {"content": suffix}}

    monkeypatch.setattr(main_mod.client, "chat", fake_chat)
    monkeypatch.setattr(main_mod.aquila_memory, "store_experience", lambda *a, **k: None)

    agent = main_mod.Agent()
    result = agent.run_unified_task("research_task", "Research topic", mode="research")

    state = read_json_state("Agent-Plans/research_task.json")
    assert state["status"] == "completed"
    report_path = os.path.join("Agent-Research", "research_task.md")
    assert os.path.exists(report_path)
    assert "Findings here" in open(report_path, encoding="utf-8").read()
