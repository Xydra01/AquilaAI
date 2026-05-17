import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from language_registry import (
    get_language,
    index_extensions,
    run_linter,
    run_tests,
)


def test_get_language_python():
    spec = get_language("src/main.py")
    assert spec is not None
    assert spec.name == "python"


def test_get_language_unknown():
    assert get_language("readme.txt") is None


def test_index_extensions_includes_multi_lang():
    exts = index_extensions()
    assert ".py" in exts
    assert ".ts" in exts
    assert ".go" in exts


def test_run_linter_python_syntax_error():
    result = run_linter("bad.py", "def oops(\n")
    assert result.status == "error"
    assert result.line is not None


@patch("language_registry._run_cmd")
def test_run_tests_pytest_pass(mock_cmd):
    mock_cmd.return_value = (0, "2 passed in 0.1s")
    result = run_tests("tests/")
    assert result.ok is True
    assert result.passed == 2


@patch("language_registry._run_cmd")
def test_run_tests_pytest_fail(mock_cmd):
    mock_cmd.return_value = (1, "1 failed, 1 passed\nFAILED test_x")
    result = run_tests("tests/")
    assert result.ok is False
    assert result.failed == 1
