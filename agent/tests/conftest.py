"""Shared pytest fixtures for Aquila OS tests."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_DIR.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(AGENT_DIR.parent))
import agent
sys.path.insert(0, str(AGENT_DIR))



def _configure_windows_utf8_stdio() -> None:
    """Prevent Rich/emoji console output from crashing pytest on cp1252 terminals."""
    if sys.platform != "win32":
        return
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def pytest_configure(config):
    _configure_windows_utf8_stdio()
    config.addinivalue_line(
        "markers",
        "harness: live harness gate tests requiring Ollama (run manually)",
    )
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(AGENT_DIR / ".env")
    except ImportError:
        pass
    # Force test-safe overrides (repo .env must not re-enable warmup mid-pytest).
    os.environ["AQUILA_WARMUP_ON_START"] = "0"
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY", "False")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Unit tests rely on mocking network calls; warmup would change call order/endpoints
    # and break test expectations when `.env` enables warmup.
    os.environ["AQUILA_SKIP_WARMUP"] = "1"


@pytest.fixture(autouse=True)
def sanitize_test_environment():
    """Prevent user shell or module-level load_dotenv from bleeding into test assertions."""
    os.environ.pop("AQUILA_DYNAMIC_LOOP", None)
    os.environ.pop("AQUILA_ALWAYS_FULL_PLAN", None)
    os.environ.pop("AQUILA_HARNESS_FORCE_MICRO_PLAN", None)
    os.environ.pop("OLLAMA_MODEL", None)
    os.environ.pop("AQUILA_TASK_EPISODE_MAX", None)
    os.environ.pop("AQUILA_REPEAT_PENALTY", None)
    os.environ.pop("AQUILA_TQ_REPEAT_PENALTY", None)
    os.environ.pop("AQUILA_STREAM_GUARD", None)
    os.environ.pop("OLLAMA_NUM_CTX", None)
    os.environ.pop("AQUILA_CONTEXT_TIER", None)
    os.environ.pop("AQUILA_KILL_SWITCH_MODE", None)
    os.environ.pop("AQUILA_LIGHT_RESEARCH_SCRAPE_CHAR_CAP", None)
    os.environ.pop("AQUILA_LIGHT_RESEARCH_MAX_READS", None)
    os.environ.pop("AQUILA_LIGHT_RESEARCH_READ_MAX_CHARS", None)
    os.environ.pop("AQUILA_LIGHT_RESEARCH_MAX_SEARCHES", None)
    os.environ.pop("AQUILA_LIGHT_RESEARCH_MAX_QUERY_WORDS", None)
    os.environ.pop("AQUILA_LIGHT_RESEARCH_USER_URL_READS", None)
    os.environ.pop("AQUILA_TIMEOUT_PER_1K_TOKENS", None)
    os.environ.pop("AQUILA_COMPACT_CHAT", None)
    os.environ.pop("LIGHT_RESEARCH_MAX_URLS", None)
    os.environ.pop("LIGHT_RESEARCH_MAX_SEARCHES", None)
    os.environ.pop("LIGHT_RESEARCH_MAX_QUERY_WORDS", None)
    os.environ.pop("LIGHT_RESEARCH_USER_URL_READS", None)
    os.environ["AQUILA_SKIP_WARMUP"] = "1"
    os.environ["AQUILA_WARMUP_ON_START"] = "0"
    # Tests should not block on user plan approval.
    os.environ["AQUILA_PLAN_REVIEW"] = "0"
    yield


def _ollama_reachable() -> bool:
    import requests

    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
    try:
        return (
            requests.get(f"{base.rstrip('/')}/api/tags", timeout=3).status_code == 200
        )
    except Exception:
        return False


def _cleanup_qt_runtime() -> None:
    """Stop GUI background threads and close top-level widgets."""
    try:
        from PySide6.QtCore import QCoreApplication, QThread
        from PySide6.QtWidgets import QApplication
    except Exception:
        return

    app = QApplication.instance()
    if app is None:
        return

    for thread in list(app.findChildren(QThread)):
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            pass

    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, 0)


def pytest_sessionfinish(session, exitstatus):
    """Hard-exit on success before Qt/Chroma destructors run (Windows 0xC0000409)."""
    if exitstatus == 0:
        os._exit(0)


@pytest.fixture(autouse=True)
def _qt_test_cleanup(request):
    yield
    mod = getattr(request.node.module, "__name__", "") or ""
    if "test_gui" in mod:
        _cleanup_qt_runtime()


@pytest.fixture(autouse=True)
def reset_singleton_caches():
    """Close Chroma clients after each test — do not eagerly reopen on setup."""
    yield
    from agent.policies import reset_runtime_context
    from agent.storage import reset_memory_cache
    from agent.core import reset_agent_instances

    reset_memory_cache()
    reset_runtime_context()
    reset_agent_instances()


@pytest.fixture(autouse=True)
def _announce_slow_agent_tests(request):
    """Agent()+Chroma indexing can take several seconds with no pytest progress output."""
    mod = getattr(request.node.module, "__name__", "") or ""
    if mod.endswith(("test_ledger_completion", "test_run_unified_task")):
        print(
            f"\n>>> Agent loop test (Chroma tool index may take ~5-15s): {request.node.name}",
            flush=True,
        )


@pytest.fixture(autouse=True)
def _announce_live_test(request):
    """Live Ollama tests can take minutes with no per-test output — log start explicitly."""
    marker = request.node.get_closest_marker("live")
    if marker is not None:
        print(f"\n>>> LIVE test (Ollama — may take several minutes): {request.node.nodeid}", flush=True)




@pytest.fixture(scope="session")
def ollama_warmed():
    """Session-scoped Ollama client with model warmed (live tests only)."""
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable")
    from agent.core import OllamaClient

    os.environ["AQUILA_SKIP_WARMUP"] = "0"
    client = OllamaClient()
    ok, msg = client.ensure_warmup()
    if not ok:
        pytest.skip(f"warmup failed: {msg}")
    return client


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
    from agent.storage import reset_memory_cache

    reset_memory_cache()
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
