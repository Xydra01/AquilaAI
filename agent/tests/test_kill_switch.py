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
    
    assert "System Timeout: Model took too long to load into VRAM" in result


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
    
    # Mock the passage of time.
    # main.py calls time.time() 4 times per loop: 
    # [Start Time, Token Print Time, Start Time Reset, Kill Switch Check Time]
    # We feed it sequential times, forcing the 4th check to be 200 seconds (triggering the 120s kill switch).
    mock_time.side_effect = [0.0, 1.0, 1.0, 200.0, 200.0, 200.0] 
    
    client = OllamaClient()
    
    result = client.chat([{"role": "user", "content": "Write an infinite loop"}], timeout=120)
    
    assert "Partial text" in result
 
    assert "Generation forcibly severed." in result