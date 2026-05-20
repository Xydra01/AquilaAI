"""LoopEngine integration: web_search auto-scrape hook."""
import json
from unittest.mock import MagicMock, patch

import pytest

from loop_engine import LoopEngine
from web_enrichment import SourceRegistry


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task_file = tmp_path / "Agent-Plans" / "t.json"
    task_file.parent.mkdir(parents=True)
    state = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": "Search web", "status": "pending", "max_iterations": 2}],
    }
    task_file.write_text(json.dumps(state), encoding="utf-8")
    return str(task_file)


@patch("loop_engine.enrich_search_result")
def test_loop_engine_calls_enrich_on_web_search(mock_enrich, tmp_ledger):
    scrape_done = {"flag": False}

    def _enrich(result, *args, **kwargs):
        scrape_done["flag"] = True
        return result + "\nAUTO-SCRAPED BLOCK"

    mock_enrich.side_effect = _enrich

    executor = MagicMock()
    executor.execute.return_value = [
        "Tool web_search returned: Search Results\nURL: https://example.com\n"
    ]

    client = MagicMock()
    client.chat.return_value = {
        "message": {"content": 'x", "tools": []}'}
    }

    engine = LoopEngine(
        client=client,
        executor=executor,
        console=MagicMock(),
        action_schema={},
        system_prompt="sys",
        mode="research",
        mode_label="Research",
        plan_dir="Agent-Plans",
    )

    def cancel_check():
        return scrape_done["flag"]

    with patch.object(engine, "_build_step_entry_messages", return_value=[]):
        with patch("loop_engine.parse_agent_response") as mock_parse:
            mock_parse.return_value = {
                "reasoning": "search",
                "tools": [{"name": "web_search", "arguments": {"query": "test"}}],
            }
            with patch("loop_engine.validate_tool_calls", return_value=(True, "")):
                with patch("loop_engine.validate_tool_arguments", return_value=(True, "")):
                    engine.run(
                        "t",
                        "topic",
                        tmp_ledger,
                        cancel_check=cancel_check,
                    )

    mock_enrich.assert_called_once()
    args = mock_enrich.call_args[0]
    assert "URL:" in args[0]
    assert isinstance(args[2], SourceRegistry)
