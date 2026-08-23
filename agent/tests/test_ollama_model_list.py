"""Tests for OllamaClient.list_models aquila filter."""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import OllamaClient


def test_list_models_filters_aquila():
    client = OllamaClient.__new__(OllamaClient)
    client.base_url = "http://127.0.0.1:11434"
    client.session = MagicMock()
    client.session.get.return_value.status_code = 200
    client.session.get.return_value.json.return_value = {
        "models": [
            {"name": "aquila_heretic:latest"},
            {"name": "llama3:latest"},
            {"name": "aquila-tq-64k:latest"},
        ]
    }
    names = client.list_models(name_filter="aquila")
    assert "llama3:latest" not in names
    assert any("aquila" in n for n in names)
    assert len(names) == 2


def test_configure_updates_fields():
    client = OllamaClient.__new__(OllamaClient)
    client.base_url = "http://127.0.0.1:11434"
    client.model_name = "aquila"
    client.num_ctx = None
    client.configure(base_url="http://127.0.0.1:11435", model_name="aquila-tq-64k")
    assert client.base_url.endswith("11435")
    assert client.model_name == "aquila-tq-64k"
