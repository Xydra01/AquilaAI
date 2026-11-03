"""Tests for env-gated semantic_search tool."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies.code_tool_catalog import get_active_code_agent_tools
from tool_library import code_agent_tools, code_canvas_tools


@pytest.fixture
def code_project(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AQUILA_DIFF_REVIEW", "0")
    code_canvas_tools.init_code_project("semtest", "", "python")
    root = tmp_path / "Agent-Code" / "semtest"
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("def run():\n    return 42\n", encoding="utf-8")
    yield root


def test_semantic_search_gated_off_by_default(monkeypatch):
    monkeypatch.delenv("AQUILA_CODE_SEMANTIC_SEARCH", raising=False)
    tools = get_active_code_agent_tools()
    assert "semantic_search" not in tools
    assert "find_files" in tools


def test_semantic_search_gated_on(monkeypatch):
    monkeypatch.setenv("AQUILA_CODE_SEMANTIC_SEARCH", "1")
    tools = get_active_code_agent_tools()
    assert "semantic_search" in tools


@patch("agent.tool_library.coding_tools.semantic_code_search")
def test_semantic_search_tool_delegates(mock_search, code_project):
    mock_search.return_value = "🔍 results"
    out = code_agent_tools.semantic_search("find run function")
    assert "results" in out
    mock_search.assert_called_once_with("find run function")


def test_index_code_project_cache(code_project):
    import agent.tool_library.coding_tools as coding_tools

    coding_tools._index_cache.clear()
    coding_tools._get_chroma_client.cache_clear()
    coding_tools._get_embedding_function.cache_clear()

    mock_collection = MagicMock()
    mock_client = MagicMock()
    mock_client.create_collection.return_value = mock_collection
    mock_client.delete_collection.return_value = None

    with patch.object(coding_tools, "_get_chroma_client", return_value=mock_client):
        with patch.object(coding_tools, "_get_embedding_function", return_value=MagicMock()):
            with patch(
                "agent.storage.embeddings.embedding_collection_tag",
                return_value="test",
            ):
                coll1 = coding_tools.index_code_project(code_project)
                meta1 = coding_tools.pop_last_index_meta()
                coll2 = coding_tools.index_code_project(code_project)
                meta2 = coding_tools.pop_last_index_meta()
    assert coll1 is coll2
    assert meta2.get("cache_hit") is True
    assert meta1.get("cache_hit") is False
