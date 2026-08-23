"""Locate Docker CLI and ensure Docker Desktop is running (Windows)."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from agent.aquila_runtime.subprocess_win import run_hidden

_SUBPROC_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


def _windows_docker_candidates() -> list[Path]:
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root:
            continue
        candidates.extend(
            [
                Path(root) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe",
                Path(root) / "Docker" / "Docker" / "resources" / "bin" / "docker",
            ]
        )
    return candidates


def _docker_desktop_exe() -> Path | None:
    for root in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        if not root:
            continue
        path = Path(root) / "Docker" / "Docker" / "Docker Desktop.exe"
        if path.is_file():
            return path
    return None


def resolve_docker_executable() -> Path | None:
    """Find ``docker`` even when the packaged app PATH omits Docker Desktop."""
    found = shutil.which("docker")
    if found:
        return Path(found)
    if os.name == "nt":
        for path in _windows_docker_candidates():
            if path.is_file():
                return path
    return None


def docker_cli_env() -> dict[str, str]:
    env = os.environ.copy()
    docker = resolve_docker_executable()
    if docker:
        env["PATH"] = str(docker.parent) + os.pathsep + env.get("PATH", "")
    return env


def is_docker_installed() -> bool:
    return resolve_docker_executable() is not None


def is_docker_daemon_running() -> tuple[bool, str]:
    """Return whether the Docker engine responds to ``docker version``."""
    if not is_docker_installed():
        return False, "docker not found"
    return _docker_version_ok(docker_cli_env())


def _docker_version_ok(env: dict[str, str]) -> tuple[bool, str]:
    docker = resolve_docker_executable()
    if not docker:
        return False, "docker not found"
    try:
        proc = run_hidden(
            [str(docker), "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=20,
            env=env,
            **_SUBPROC_KW,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "docker version failed").strip()
        return False, msg[:200]
    return True, (proc.stdout or "").strip() or "ok"


def launch_docker_desktop() -> tuple[bool, str]:
    """Start Docker Desktop on Windows if installed but not running."""
    if os.name != "nt":
        return False, "auto-start is supported on Windows only"
    exe = _docker_desktop_exe()
    if not exe:
        return False, "Docker Desktop not installed"
    try:
        subprocess.Popen(
            [str(exe)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except PermissionError as exc:
        return False, (
            f"Access denied starting Docker Desktop ({exc}). "
            "If Docker is already running under another Windows account, "
            "skip web search for this user or start Aquila while that session owns Docker."
        )
    except OSError as exc:
        err = str(exc)
        low = err.lower()
        if "access is denied" in low or "access denied" in low or "winerror 5" in low:
            return False, (
                f"Access denied starting Docker Desktop ({err}). "
                "If Docker is already running under another Windows account, "
                "skip web search for this user or start Aquila while that session owns Docker."
            )
        return False, err
    return True, "Starting Docker Desktop…"


def ensure_docker_daemon(*, wait_seconds: float = 90.0) -> tuple[bool, str]:
    """
    Ensure docker CLI works. On Windows, start Docker Desktop if the daemon is down.
    """
    if not is_docker_installed():
        return False, "Docker not installed"
    env = docker_cli_env()
    ok, msg = _docker_version_ok(env)
    if ok:
        return True, "Docker is running"
    if os.name == "nt" and _docker_desktop_exe():
        started, note = launch_docker_desktop()
        if not started:
            return False, note
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            ok, msg = _docker_version_ok(env)
            if ok:
                return True, "Docker is running"
            time.sleep(2.0)
        return False, (
            "Docker Desktop was started but the engine is not ready yet. "
            "Wait for the whale icon to turn steady, then retry."
        )
    return False, msg or "Docker daemon not running"
