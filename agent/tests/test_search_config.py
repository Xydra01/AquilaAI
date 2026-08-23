"""Tests for search_config helpers."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.storage import RuntimeSettings, save_runtime_settings
from agent.research import get_engines, get_search_url, search_params


def test_search_params_from_settings(tmp_path, monkeypatch):
    inst = tmp_path / "Agent-Instances"
    inst.mkdir(parents=True)
    monkeypatch.setattr(
        "runtime_settings.agent_data_path",
        lambda *parts: inst.joinpath(*parts) if parts else inst,
    )
    save_runtime_settings(
        RuntimeSettings(
            searxng_base_url="http://search.local:9090",
            searxng_engines="duckduckgo,wikipedia",
        ),
        sync_env=False,
    )
    assert get_search_url() == "http://search.local:9090"
    assert get_engines() == "duckduckgo,wikipedia"
    params = search_params("docker imap")
    assert params["q"] == "docker imap"
    assert params["engines"] == "duckduckgo,wikipedia"


@patch("agent.research.search_config.resolve_docker_executable", return_value=None)
def test_docker_status_unavailable(mock_resolve):
    from agent.research import docker_status

    status = docker_status()
    assert status["available"] is False
