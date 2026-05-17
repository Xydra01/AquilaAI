import pytest
import sys
import os
import requests
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import OllamaClient

@patch('main.requests.Session.post')
def test_vram_load_timeout(mock_post):
    """
    TDD Goal: If the initial POST request takes too long (e.g., model loading into VRAM),
    it should catch ReadTimeout and safely return the VRAM error string.
    """
    mock_post.side_effect = requests.exceptions.ReadTimeout("Hardware Timeout")
    
    client = OllamaClient()
    result = client.chat([{"role": "user", "content": "Hello"}])
    
    assert "System Timeout: Model took too long to load into VRAM" in result["message"]["content"]

@patch('main.requests.Session.post')
@patch('main.time.time')
def test_generation_kill_switch(mock_time, mock_post):
    """
    TDD Goal: If token generation takes longer than the timeout limit (default 120s), 
    the OS must manually sever the connection and return the partial content.
    """
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [b'data: {"choices": [{"delta": {"content": "Partial text"}}]}']
    mock_post.return_value = mock_response
    
    mock_time.side_effect = [0.0, 1.0, 1.0, 200.0, 200.0, 200.0] 
    
    client = OllamaClient()
    generator = client.chat([{"role": "user", "content": "Write an infinite loop"}], timeout=120, stream=True)
    
    chunks = list(generator)
    full_text = "".join([c["message"]["content"] for c in chunks])
    
    assert "Partial text" in full_text
    assert "Generation forcibly severed." in full_text