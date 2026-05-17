import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch

# Add the parent 'agent' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import read_file, write_file, replace_in_file, list_directory

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """
    Creates a sandboxed workspace for the tools to operate in.
    Physically changes the CWD so the tools don't write to the real filesystem.
    """
    workspace_dir = tmp_path / "sandbox"
    workspace_dir.mkdir()
    
    # Monkeypatch the current working directory to force tools into the sandbox!
    monkeypatch.chdir(workspace_dir)
    
    with patch('tools.AGENT_ROOT_DIR', workspace_dir):
        yield workspace_dir

# --- 1. Testing write_file ---

def test_write_file_success(workspace):
    """TDD Goal: Ensure write_file correctly creates and writes to a file."""
    # Removed the trailing newline here since the tool strips it
    result = write_file("test_script.py", "print('Hello World')")
    
    assert "Successfully" in result
    
    # Verify the file actually exists on disk in the sandbox
    saved_file = workspace / "test_script.py"
    assert saved_file.exists()
    assert saved_file.read_text() == "print('Hello World')"

def test_write_file_forbidden_path(workspace):
    """TDD Goal: Ensure write_file respects the security firewall."""
    result = write_file(".env", "SECRET=123")
    assert "SECURITY BLOCK" in result or "Security Error" in result or "forbidden" in result.lower()
    
    # Verify the malicious file was NEVER created
    assert not (workspace / ".env").exists()

# --- 2. Testing read_file ---

def test_read_file_success(workspace):
    """TDD Goal: Ensure read_file correctly reads an existing file."""
    # Create a dummy file first
    dummy_file = workspace / "dummy.txt"
    dummy_file.write_text("Line 1\nLine 2")
    
    result = read_file("dummy.txt")
    assert "Line 1\nLine 2" in result

def test_read_file_not_found(workspace):
    """TDD Goal: Ensure reading a non-existent file returns a safe string, not a Python Exception."""
    result = read_file("does_not_exist.txt")
    assert "Error: File" in result
    assert "not found" in result

def test_read_file_forbidden_path(workspace):
    """TDD Goal: Ensure read_file respects the security firewall."""
    result = read_file("state.json")
    assert "SECURITY BLOCK" in result or "Security Error" in result or "forbidden" in result.lower()

# --- 3. Testing replace_in_file ---

def test_replace_in_file_success(workspace):
    """TDD Goal: Ensure replace_in_file correctly swaps out text."""
    dummy_file = workspace / "script.py"
    dummy_file.write_text("def add(a, b):\n    return a + b")
    
    result = replace_in_file("script.py", "return a + b", "return a + b + 1")
    
    assert "Successfully replaced" in result
    assert dummy_file.read_text() == "def add(a, b):\n    return a + b + 1"

def test_replace_in_file_target_not_found(workspace):
    """TDD Goal: Ensure it safely rejects replacements if the target string is wrong."""
    dummy_file = workspace / "script.py"
    dummy_file.write_text("def add(a, b):\n    return a + b")
    
    # The LLM hallucinated the target text slightly
    result = replace_in_file("script.py", "return a+b", "return a + b + 1")
    
    assert "Error" in result
    assert "exact target text was not found" in result
    # Ensure the file was left completely untouched
    assert dummy_file.read_text() == "def add(a, b):\n    return a + b"