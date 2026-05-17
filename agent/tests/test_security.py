import pytest
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import is_safe_path

def test_allowed_paths():
    """TDD Goal: Ensure normal workspace files are permitted."""
    assert is_safe_path(Path("my_script.py")) is True
    assert is_safe_path(Path("Agent-Tasks/task_123.json")) is True
    assert is_safe_path(Path("Agent-Creations/final_report.md")) is True
    assert is_safe_path(Path("src/utils/helpers.py")) is True

def test_forbidden_exact_files():
    """TDD Goal: Ensure highly sensitive files are blocked by exact name."""
    assert is_safe_path(Path(".env")) is False
    assert is_safe_path(Path("state.json")) is False
    assert is_safe_path(Path("chroma.sqlite3")) is False
    assert is_safe_path(Path("some/nested/folder/.env")) is False

def test_forbidden_extensions():
    """TDD Goal: Ensure sensitive file types are blocked by extension."""
    assert is_safe_path(Path("keys/aws_secret.pem")) is False
    assert is_safe_path(Path("database.sqlite3")) is False
    assert is_safe_path(Path("server.log")) is False
    assert is_safe_path(Path("Agent-Tasks/crash_dump.db")) is False

def test_forbidden_directories():
    """TDD Goal: Ensure the agent cannot traverse into system directories."""
    assert is_safe_path(Path("Agent-Logs/session_1.txt")) is False
    assert is_safe_path(Path("vector_db/data.bin")) is False
    assert is_safe_path(Path(".git/config")) is False
    assert is_safe_path(Path("__pycache__/main.cpython-310.pyc")) is False