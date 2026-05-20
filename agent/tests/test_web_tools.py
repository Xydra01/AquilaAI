import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tool_library import web_tools

@patch('tool_library.web_tools.requests.get')
def test_web_search_success(mock_get):
    """TDD Goal: Ensure web_search correctly parses JSON results from SearXNG."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"title": "Aquila AI Framework", "url": "https://example.com/aquila", "content": "A powerful autonomous OS."}
        ]
    }
    mock_get.return_value = mock_response

    result = web_tools.web_search("Aquila OS")
    
    assert "Aquila AI Framework" in result
    assert "https://example.com/aquila" in result
    assert "A powerful autonomous OS." in result

@patch('tool_library.web_tools.requests.get')
def test_web_search_no_results(mock_get):
    """TDD Goal: Ensure web_search safely handles empty responses."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_get.return_value = mock_response

    result = web_tools.web_search("super obscure impossible query")
    assert "No results found" in result

@patch('tool_library.web_tools.cloudscraper.create_scraper')
def test_read_webpage_html(mock_create_scraper):
    """TDD Goal: Ensure read_webpage extracts HTML, strips scripts, and converts to Markdown."""
    mock_scraper = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {'Content-Type': 'text/html'}
    
    mock_response.text = "<html><body><h1>Main Title</h1><script>alert('bad');</script><p>Some content.</p></body></html>"
    
    mock_scraper.get.return_value = mock_response
    mock_create_scraper.return_value = mock_scraper

    result = web_tools.read_webpage("https://example.com")
    
    assert "Main Title" in result
    assert "Some content" in result
    assert "alert('bad')" not in result


@patch('tool_library.web_tools.cloudscraper.create_scraper')
def test_read_webpage_truncates_with_max_chars(mock_create_scraper):
    mock_scraper = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {'Content-Type': 'text/html'}
    mock_response.text = "<html><body><p>" + ("word " * 5000) + "</p></body></html>"
    mock_scraper.get.return_value = mock_response
    mock_create_scraper.return_value = mock_scraper

    result = web_tools.read_webpage("https://example.com", max_chars=500)
    assert "...[CONTENT TRUNCATED]" in result
    assert len(result) < 800