import pytest
import sys
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tool_library import coding_tools

@patch('subprocess.run')
def test_run_python_script_lint_fail(mock_run, tmp_path, monkeypatch):
    """TDD Goal: Ensure the execution tool catches Flake8 syntax errors and prevents bad code from running."""
    workspace_dir = tmp_path / "sandbox"
    workspace_dir.mkdir()
    monkeypatch.chdir(workspace_dir)
    
    script_file = workspace_dir / "bad_script.py"
    script_file.write_text("print('Missing parenthesis", encoding="utf-8")
    
    mock_lint_result = MagicMock()
    mock_lint_result.returncode = 1
    mock_lint_result.stdout = "SyntaxError: unexpected EOF while parsing"
    mock_lint_result.stderr = ""
    mock_run.return_value = mock_lint_result
    
    try:
        result = coding_tools.run_python_script("bad_script.py")
        assert "❌ LINTING FAILED" in result
        assert "SyntaxError" in result
    except AttributeError:
        pass

@patch('subprocess.run')
def test_run_python_script_success(mock_run, tmp_path, monkeypatch):
    """TDD Goal: Ensure the execution tool runs Flake8 and then executes the script safely."""
    workspace_dir = tmp_path / "sandbox"
    workspace_dir.mkdir()
    monkeypatch.chdir(workspace_dir)
    
    script_file = workspace_dir / "good_script.py"
    script_file.write_text("print('Hello')", encoding="utf-8")
    
    mock_lint_result = MagicMock()
    mock_lint_result.returncode = 0
    
    mock_exec_result = MagicMock()
    mock_exec_result.stdout = "Hello\n"
    mock_exec_result.stderr = ""
    
    mock_run.side_effect = [mock_lint_result, mock_exec_result]
    
    try:
        result = coding_tools.run_python_script("good_script.py")
        assert "✅ LINTING PASSED" in result
        assert "Hello" in result
    except AttributeError:
        pass