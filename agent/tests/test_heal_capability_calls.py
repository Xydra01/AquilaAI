"""Tests for capability call healing (nested id / arg-shape mixups)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities.heal_calls import heal_capability_call, heal_capability_calls


def test_heal_prefers_nested_create_file_over_run_tests():
    healed = heal_capability_call(
        {
            "id": "cap.dev.run_tests@v1",
            "arguments": {
                "id": "cap.dev.create_file@v1",
                "file_path": "tests/test_habit.py",
                "content": "def test_x():\n    assert False\n",
            },
        }
    )
    assert healed is not None
    assert healed["id"] == "cap.dev.create_file@v1"
    assert healed["arguments"]["file_path"] == "tests/test_habit.py"
    assert "id" not in healed["arguments"]


def test_heal_prefers_nested_recon_over_project_setup():
    healed = heal_capability_call(
        {
            "id": "cap.dev.project_setup@v1",
            "arguments": {"id": "cap.dev.recon@v1", "directory": "."},
        }
    )
    assert healed is not None
    assert healed["id"] == "cap.dev.recon@v1"
    assert healed["arguments"].get("directory") == "."


def test_heal_infers_create_file_from_args_without_id():
    healed = heal_capability_call(
        {
            "arguments": {
                "file_path": "habit.py",
                "content": "print('hi')\n",
                "create_file": True,
            }
        }
    )
    assert healed is not None
    assert healed["id"] == "cap.dev.create_file@v1"
    assert "create_file" not in healed["arguments"]


def test_heal_capability_calls_batch():
    out = heal_capability_calls(
        [
            {
                "id": "cap.dev.run_tests@v1",
                "arguments": {
                    "id": "cap.dev.create_file@v1",
                    "file_path": "a.py",
                    "content": "x",
                },
            }
        ]
    )
    assert len(out) == 1
    assert out[0]["id"] == "cap.dev.create_file@v1"


def test_heal_normalizes_args_key():
    healed = heal_capability_call(
        {
            "id": "cap.dev.create_file@v1",
            "args": {"file_path": "habit.py", "content": "print('hi')\n"},
        }
    )
    assert healed is not None
    assert healed["arguments"]["file_path"] == "habit.py"
    assert "args" not in healed


def test_capability_call_model_normalizes_args_key():
    from agent.parser.structured_schema import CapabilityCallModel

    model = CapabilityCallModel.model_validate(
        {
            "id": "cap.dev.create_file@v1",
            "args": {"file_path": "x.py", "content": "y"},
        }
    )
    assert model.arguments["file_path"] == "x.py"
