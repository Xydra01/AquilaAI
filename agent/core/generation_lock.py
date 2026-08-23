"""Cross-process lock so GUI, Remote, and MCP host share one Ollama generation."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from agent.storage import agent_data_path


class GenerationBusyError(Exception):
    """Raised when another process holds the generation lock."""

    def __init__(self, info: dict | None = None):
        self.info = info or {}
        src = self.info.get("source", "unknown")
        pid = self.info.get("pid", "?")
        super().__init__(
            f"Another Aquila generation is running (source={src}, pid={pid})."
        )


_local = threading.local()


@dataclass
class LockInfo:
    pid: int
    source: str
    host: str
    started_at: float

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "source": self.source,
            "host": self.host,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LockInfo:
        return cls(
            pid=int(data.get("pid", 0)),
            source=str(data.get("source", "unknown")),
            host=str(data.get("host", "")),
            started_at=float(data.get("started_at", 0)),
        )


def _lock_path():
    path = agent_data_path("Agent-Instances") / "generation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def read_lock_info() -> LockInfo | None:
    path = _lock_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return LockInfo.from_dict(data)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass
    return None


def is_generation_busy(*, ignore_own_pid: bool = True) -> bool:
    info = read_lock_info()
    if info is None:
        return False
    if ignore_own_pid and info.pid == os.getpid():
        return False
    if not _pid_alive(info.pid):
        return False
    return True


def busy_payload() -> dict:
    info = read_lock_info()
    if info is None:
        return {"status": "busy", "message": "Generation lock held (unknown owner)."}
    return {
        "status": "busy",
        "message": (
            f"Another Aquila generation is running "
            f"(source={info.source}, pid={info.pid})."
        ),
        "lock": info.to_dict(),
    }


def _clear_stale_lock() -> None:
    info = read_lock_info()
    if info is None:
        return
    if info.pid == os.getpid():
        return
    if not _pid_alive(info.pid):
        try:
            _lock_path().unlink(missing_ok=True)
        except OSError:
            pass


def try_acquire(source: str) -> bool:
    """Acquire lock or return False if another live process holds it."""
    _clear_stale_lock()
    path = _lock_path()
    payload = LockInfo(
        pid=os.getpid(),
        source=(source or "unknown").strip() or "unknown",
        host=socket.gethostname(),
        started_at=time.time(),
    ).to_dict()
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
        try:
            os.write(fd, json.dumps(payload).encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        info = read_lock_info()
        if info and info.pid == os.getpid():
            return True
        if info and not _pid_alive(info.pid):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return try_acquire(source)
        return False


def release() -> None:
    info = read_lock_info()
    if info is None:
        return
    if info.pid != os.getpid():
        return
    try:
        _lock_path().unlink(missing_ok=True)
    except OSError:
        pass


@contextmanager
def generation_lock(source: str = "unknown") -> Iterator[None]:
    depth = int(getattr(_local, "depth", 0) or 0)
    acquired_here = False
    if depth == 0:
        if not try_acquire(source):
            info = read_lock_info()
            raise GenerationBusyError(info.to_dict() if info else None)
        acquired_here = True
    _local.depth = depth + 1
    try:
        yield
    finally:
        _local.depth = max(0, _local.depth - 1)
        if acquired_here:
            release()
