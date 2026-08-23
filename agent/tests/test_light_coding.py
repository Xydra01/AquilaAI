"""Unit tests for Chat Mode light coding."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.coding import (
    LightCodingConfig,
    build_light_coding_context,
    invalidate_session_cache,
    load_light_coding_config,
)


@pytest.fixture(autouse=True)
def _clear_light_coding_cache():
    invalidate_session_cache()
    yield
    invalidate_session_cache()


def test_load_light_coding_config_defaults(monkeypatch):
    monkeypatch.delenv("AQUILA_LIGHT_CODING_TOKEN_BUDGET", raising=False)
    cfg = load_light_coding_config()
    assert cfg.token_budget == 20000
    assert cfg.max_files_full == 40
    assert cfg.file_char_cap == 12000


def test_build_light_coding_context_respects_token_budget(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n" * 50, encoding="utf-8")
    for i in range(8):
        (tmp_path / f"module_{i}.py").write_text(
            f"def fn_{i}():\n    return {i}\n" + ("# pad\n" * 400),
            encoding="utf-8",
        )

    cfg = LightCodingConfig(
        token_budget=500,
        max_files_full=20,
        file_char_cap=2000,
        max_walk_files=100,
        grep_max=5,
    )
    block, stats = build_light_coding_context(str(tmp_path), "module_3", config=cfg)

    assert block
    assert stats["tokens_used"] <= cfg.token_budget + 50
    assert stats["files_full"] >= 1
    assert "Remaining files" in block or stats["files_summary"] >= 0


def test_build_light_coding_skips_ignored_paths(tmp_path):
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "ignored.py").write_text("secret = True\n", encoding="utf-8")
    node = tmp_path / "node_modules" / "pkg"
    node.mkdir(parents=True)
    (node / "index.js").write_text("module.exports = {}\n", encoding="utf-8")

    block, stats = build_light_coding_context(str(tmp_path), config=LightCodingConfig())
    assert stats["files_walked"] == 1
    assert "good.py" in block
    assert "ignored.py" not in block
    assert "node_modules" not in block


def test_build_light_coding_prioritizes_readme(tmp_path):
    (tmp_path / "zzz.py").write_text("z = 0\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Important readme\n", encoding="utf-8")

    cfg = LightCodingConfig(token_budget=20000, max_files_full=1, file_char_cap=5000)
    block, stats = build_light_coding_context(str(tmp_path), config=cfg)

    assert stats["files_full"] == 1
    assert "README.md" in block
    assert stats["files_summary"] >= 1


@patch("agent.coding.build_light_coding_context")
def test_run_light_coding_chat_injects_block(mock_build):
    from agent.core import Agent

    mock_build.return_value = ("def hello(): pass", {"tokens_used": 10})
    agent = MagicMock(spec=Agent)
    agent.instance_id = "test-instance"
    agent.memory = MagicMock()
    agent.memory.get_all_facts.return_value = ""
    agent.memory.recall_experiences.return_value = ""
    agent.client = MagicMock()
    agent.client.chat.return_value = iter([])

    from agent.core import Agent as RealAgent

    RealAgent.run_light_coding_chat(
        agent,
        "what does hello do?",
        chat_history=[],
        stream=True,
        repo_root="/tmp/repo",
    )

    messages = agent.client.chat.call_args[0][0]
    assert any("CODE CONTEXT (light)" in (m.get("content") or "") for m in messages)
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "what does hello do?"


def test_agent_worker_routes_light_coding(qtbot, qapp):
    from agent import gui

    worker = gui.AgentWorker(
        task_name="lc",
        prompt="What is X?",
        mode="chat",
        light_coding=True,
        light_coding_repo="/tmp/repo",
        light_coding_block="--- FILE: x.py ---\nx=1",
    )
    mock_agent = MagicMock()
    mock_agent.run_light_coding_chat.return_value = iter(
        [{"message": {"content": "Answer"}}]
    )

    with patch("gui.get_agent", return_value=mock_agent):
        with qtbot.waitSignal(worker.finished_signal, timeout=3000):
            worker.start()

    mock_agent.run_light_coding_chat.assert_called_once()
    mock_agent.run_chat.assert_not_called()
    mock_agent.run_light_research_chat.assert_not_called()
