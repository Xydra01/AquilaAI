"""Tests for Ollama model discovery across engine URLs."""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import OllamaClient


def test_discover_aquila_models_falls_back_to_other_port():
    client = OllamaClient.__new__(OllamaClient)
    client.base_url = "http://127.0.0.1:11435"
    client.session = MagicMock()

    def fake_get(url, timeout=5):
        resp = MagicMock()
        if url.endswith("11435/api/tags"):
            resp.status_code = 200
            resp.json.return_value = {"models": []}
        elif url.endswith("11434/api/tags"):
            resp.status_code = 200
            resp.json.return_value = {
                "models": [
                    {"name": "aquila:latest"},
                    {"name": "aquila_heretic:latest"},
                ]
            }
        else:
            raise ConnectionError("refused")
        return resp

    client.session.get.side_effect = fake_get
    detail = client.discover_aquila_models(primary_base_url="http://127.0.0.1:11435")
    assert detail["models"] == ["aquila:latest", "aquila_heretic:latest"]
    assert "11434" in detail["base_url"]


def test_list_models_detailed_reports_unreachable():
    client = OllamaClient.__new__(OllamaClient)
    client.base_url = "http://127.0.0.1:11434"
    client.session = MagicMock()
    client.session.get.side_effect = ConnectionError("refused")
    detail = client.list_models_detailed(base_url="http://127.0.0.1:11434")
    assert detail["reachable"] is False
    assert "Cannot reach" in detail["error"]
