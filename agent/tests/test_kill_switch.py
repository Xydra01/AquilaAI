import json
import pytest
import sys
import os
import requests
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agent.core import OllamaClient

@patch("main.console.log_filename", None)
@patch('main.requests.Session.post')
def test_vram_load_timeout(mock_post):
    """
    TDD Goal: If the initial POST request takes too long (e.g., model loading into VRAM),
    it should catch ReadTimeout and safely return the VRAM error string.
    """
    mock_post.side_effect = requests.exceptions.ReadTimeout("Hardware Timeout")
    
    client = OllamaClient()
    result = client.chat([{"role": "user", "content": "Hello"}])
    
    assert "System Timeout" in result["message"]["content"]
    assert "VRAM" in result["message"]["content"]

def test_generation_kill_switch():
    """
    TDD Goal: If token generation takes longer than the timeout limit (default 120s),
    the OS must manually sever the connection and return the partial content.
    """
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [
        json.dumps({"message": {"content": "Partial text"}}).encode(),
        b"",
    ]

    clock = {"n": 0}

    def fake_time():
        clock["n"] += 1
        # Deterministic time progression for "stall/no progress" logic.
        # Each internal time() call advances by 100s so the kill triggers
        # on the subsequent empty-line iteration.
        return float(clock["n"] * 100)

    with patch("main.console.log_filename", None), patch("main.console.print"), patch(
        "main.time.time", side_effect=fake_time
    ), patch("main.requests.Session.post", return_value=mock_response), patch.object(
        OllamaClient, "_log_model_availability"
    ), patch("main.OllamaClient.probe", return_value=True):
        client = OllamaClient()
        generator = client.chat(
            [{"role": "user", "content": "Write an infinite loop"}],
            timeout=50,
            stream=True,
        )

        chunks = list(generator)
        full_text = "".join([c["message"]["content"] for c in chunks])

    assert "Partial text" in full_text
    assert "Generation forcibly severed." in full_text
