import pytest
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import initiate_sleep_cycle

@patch('main.client.chat')
@patch('main.aquila_memory.store_experience')
def test_sleep_cycle_parses_dictionary(mock_store, mock_chat, tmp_path):
    """TDD Goal: Ensure Sleep Cycle safely extracts string from the LLM dictionary."""
    
    # 1. Setup a fake task file in a temporary directory
    tasks_dir = tmp_path / "Agent-Tasks"
    tasks_dir.mkdir()
    fake_task = tasks_dir / "test_task.json"
    fake_task.write_text(json.dumps({"status": "completed"}))
    
    # 2. Mock the DICTIONARY response from the LLM
    mock_chat.return_value = {"message": {"content": "Task was successfully completed."}}
    
    # 3. Temporarily patch the hardcoded Path inside initiate_sleep_cycle to use our tmp_path
    with patch('main.Path') as mock_path:
        mock_path.return_value = tasks_dir
        
        # 4. Run sleep cycle
        results = initiate_sleep_cycle()
        
        # 5. Verify it passed the STRING to memory, not the dictionary!
        assert "Compressed and cleared" in results
        mock_store.assert_called_once_with("Agent-Tasks/test_task", "Task was successfully completed.")


@patch("main.client.chat")
@patch("main.aquila_memory.store_experience")
def test_sleep_cycle_includes_agent_plans(mock_store, mock_chat, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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