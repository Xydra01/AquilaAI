import pytest
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import initiate_sleep_cycle

@patch('main.client.chat')
@patch('main.aquila_memory.store_experience')
def test_sleep_cycle_parses_dictionary(mock_store, mock_chat, tmp_path, monkeypatch):
    """TDD Goal: Ensure Sleep Cycle safely extracts string from the LLM dictionary."""
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    tasks_dir = tmp_path / "Agent-Tasks"
    tasks_dir.mkdir()
    fake_task = tasks_dir / "test_task.json"
    fake_task.write_text(json.dumps({"status": "completed"}))

    mock_chat.return_value = {"message": {"content": "Task was successfully completed."}}

    results = initiate_sleep_cycle()

    assert "Compressed and cleared" in results
    mock_store.assert_called_once_with("Agent-Tasks/test_task", "Task was successfully completed.")


@patch("main.client.chat")
@patch("main.aquila_memory.store_experience")
def test_sleep_cycle_includes_agent_plans(mock_store, mock_chat, tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    tasks_dir = tmp_path / "Agent-Tasks"
    plans_dir = tmp_path / "Agent-Plans"
    tasks_dir.mkdir()
    plans_dir.mkdir()
    (tasks_dir / "task_a.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (plans_dir / "plan_b.json").write_text(json.dumps({"status": "in_progress"}), encoding="utf-8")

    mock_chat.return_value = {"message": {"content": "Consolidated."}}

    results = initiate_sleep_cycle()

    assert "Agent-Plans/plan_b" in results
    assert not (plans_dir / "plan_b.json").exists()
    assert mock_store.call_count == 2