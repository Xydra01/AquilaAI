import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    GenerationBusyError,
    busy_payload,
    generation_lock,
    is_generation_busy,
    read_lock_info,
    release,
    try_acquire,
)


@pytest.fixture
def isolated_lock(tmp_path, monkeypatch):
    lock_dir = tmp_path / "Agent-Instances"
    lock_dir.mkdir()
    lock_file = lock_dir / "generation.lock"
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    return lock_file


def test_acquire_and_release(isolated_lock):
    assert try_acquire("test")
    assert isolated_lock.is_file()
    assert is_generation_busy(ignore_own_pid=False)
    release()
    assert not isolated_lock.is_file()


def test_busy_when_other_pid_alive(isolated_lock, monkeypatch):
    import sys
    gen_lock_mod = sys.modules['agent.core.generation_lock']
    assert try_acquire("first")
    other_pid = os.getpid() + 99999
    isolated_lock.write_text(
        f'{{"pid": {other_pid}, "source": "other", "host": "x", "started_at": 0}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gen_lock_mod,
        "_pid_alive",
        lambda pid: pid == other_pid,
    )
    assert not try_acquire("second")
    payload = busy_payload()
    assert payload["status"] == "busy"


def test_reentrant_same_process(isolated_lock):
    with generation_lock("outer"):
        with generation_lock("inner"):
            assert isolated_lock.is_file()
    assert not isolated_lock.is_file()


def test_context_manager_raises_when_busy(isolated_lock, monkeypatch):
    import sys
    gen_lock_mod = sys.modules['agent.core.generation_lock']
    isolated_lock.write_text(
        f'{{"pid": 999999, "source": "blocker", "host": "x", "started_at": 0}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(gen_lock_mod, "_pid_alive", lambda pid: True)
    with pytest.raises(GenerationBusyError):
        with generation_lock("test"):
            pass


