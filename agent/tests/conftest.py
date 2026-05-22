"""Shared pytest fixtures for Aquila OS tests."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_DIR.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(AGENT_DIR))


def pytest_configure(config):
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(AGENT_DIR / ".env")
    except ImportError:
        pass




@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(autouse=True)
def reset_dual_logger():
    """Prevent cross-test log path bleed (tmp dirs deleted while console still references them)."""
    import main as main_mod

    main_mod.console.log_filename = None
    main_mod.console.jsonl_filename = None
    main_mod.console.current_task = None
    yield
    main_mod.console.log_filename = None
    main_mod.console.jsonl_filename = None
    main_mod.console.current_task = None


@pytest.fixture
def tmp_agent_dirs(tmp_path, monkeypatch):
    """Isolated Agent-* working directories for filesystem tests."""
    for name in (
        "Agent-Tasks",
        "Agent-Plans",
        "Agent-Drafts",
        "Agent-Creations",
        "Agent-Research",
        "Agent-Logs",
        "Agent-Memory",
    ):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def sample_ledger():
    def _factory(
        steps=None,
        current_step_index=0,
        status="in_progress",
    ):
        if steps is None:
            steps = [
                {"description": "Step one", "status": "pending", "max_iterations": 3},
                {"description": "Step two", "status": "pending", "max_iterations": 2},
            ]
        return {
            "status": status,
            "current_step_index": current_step_index,
            "steps": steps,
        }

    return _factory


@pytest.fixture
def write_ledger(tmp_agent_dirs):
    def _write(rel_path: str, state: dict):
        path = tmp_agent_dirs / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def mock_ollama_chat():
    """Patch main.client.chat with a configurable mock."""

    def _patch(return_value=None, stream_chunks=None):
        if stream_chunks is not None:

            def stream_gen(*args, **kwargs):
                for chunk in stream_chunks:
                    yield chunk

            return stream_gen

        if return_value is None:
            return_value = {"message": {"content": '{"reasoning":"ok","tools":[]}'}}
        return MagicMock(return_value=return_value)

    return _patch


def load_fixture_ledger(name: str) -> dict:
    path = FIXTURES_DIR / "ledgers" / name
    return json.loads(path.read_text(encoding="utf-8"))
