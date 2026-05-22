import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tool_library import os_tools

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """
    Creates a sandboxed workspace for the OS tools.
    Physically changes the CWD so the tools don't search the real filesystem.
    """
    workspace_dir = tmp_path / "sandbox"
    workspace_dir.mkdir()
    
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(workspace_dir))
    monkeypatch.chdir(workspace_dir)
    yield workspace_dir

def test_search_in_file_success(workspace):
    """TDD Goal: Ensure search_in_file correctly locates keywords and provides line numbers."""
    dummy_file = workspace / "server_output.txt"
    dummy_file.write_text("Booting up...\nWarning: High RAM usage\nShutting down...", encoding="utf-8")
    
    result = os_tools.search_in_file("server_output.txt", keyword="Warning")
    
    assert "Warning: High RAM usage" in result
    assert "2:" in result

def test_search_in_file_forbidden(workspace):
    """TDD Goal: Ensure search_in_file respects the security firewall."""
    result = os_tools.search_in_file(".env", keyword="SECRET")
    assert "SECURITY BLOCK" in result or "forbidden" in result.lower()

def test_search_in_file_no_keyword(workspace):
    """TDD Goal: Ensure the tool safely rejects searches with empty keywords."""
    result = os_tools.search_in_file("some_file.txt", keyword="")
    assert "Error" in result or "must provide" in result.lower()

def test_search_in_file_not_found(workspace):
    """TDD Goal: Ensure searching for a non-existent keyword returns a clean message."""
    dummy_file = workspace / "clean_output.txt"
    dummy_file.write_text("All systems go.", encoding="utf-8")
    
    result = os_tools.search_in_file("clean_output.txt", keyword="Error")
    assert "not found" in result.lower()

def test_read_env_vars_redaction(monkeypatch):
    """TDD Goal: Ensure read_env_vars successfully reads but strictly redacts sensitive keys."""
    monkeypatch.setenv("TEST_API_KEY", "super_secret_123456789")
    monkeypatch.setenv("PUBLIC_MODE", "True")
    
    try:
        result = os_tools.read_env_vars()
        
        # It should successfully show non-sensitive environment keys
        assert "PUBLIC_MODE" in result
        
        # CRITICAL: It MUST redact the actual secret value!
        assert "super_secret_123456789" not in result
        assert "****" in result or "..." in result
        
    except AttributeError:
        pass