"""SearXNG URL/engines from runtime settings + optional Docker control."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import requests

from agent.aquila_runtime.subprocess_win import run_hidden

from agent.aquila_runtime.docker_desktop import (
    docker_cli_env,
    ensure_docker_daemon,
    is_docker_daemon_running,
    is_docker_installed,
    resolve_docker_executable,
)
from agent.aquila_runtime.search_bundle import ensure_search_support_files, search_support_dir
from agent.storage import active_search_config, load_runtime_settings, save_runtime_settings

_SERVICE_NAME = "aquila-search"
_SUBPROC_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


def get_search_url() -> str:
    return active_search_config()["base_url"].rstrip("/")


def get_engines() -> str:
    return active_search_config()["engines"]


def search_params(query: str, *, extra: dict[str, str] | None = None) -> dict[str, str]:
    params = {
        "q": query,
        "format": "json",
        "engines": get_engines(),
        "language": "en",
    }
    if extra:
        params.update(extra)
    return params


def probe_health(*, timeout: float = 5.0) -> tuple[bool, str]:
    base = get_search_url()
    try:
        resp = requests.get(
            f"{base}/search",
            params={"q": "test", "format": "json"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return True, "SearXNG responded OK"
        return False, f"HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return False, str(exc)


def compose_path() -> Path:
    return search_support_dir() / "docker-compose.yml"


def _docker_cmd(*, require_compose: bool = True) -> list[str] | None:
    docker = resolve_docker_executable()
    if not docker:
        return None
    if require_compose:
        compose = compose_path()
        if not compose.is_file():
            return None
        return [str(docker), "compose", "-f", str(compose)]
    return [str(docker)]


def docker_status() -> dict[str, Any]:
    if not resolve_docker_executable():
        return {"available": False, "running": False, "message": "Docker executable not found"}
    if not is_docker_installed():
        compose = compose_path()
        if not compose.is_file():
            return {
                "available": False,
                "running": False,
                "message": "docker-compose.yml not installed (optional web search)",
            }
        return {
            "available": False,
            "running": False,
            "message": "Docker not installed (optional web search)",
        }
    ok, msg = is_docker_daemon_running()
    if not ok:
        return {
            "available": True,
            "running": False,
            "message": (
                "Docker is installed but not running — use Start container "
                "or open Docker Desktop"
            ),
        }
    cmd = _docker_cmd()
    if not cmd:
        return {
            "available": True,
            "running": False,
            "message": "Search config not installed yet",
        }
    env = docker_cli_env()
    try:
        proc = run_hidden(
            [*cmd, "ps", _SERVICE_NAME, "--format", "json"],
            capture_output=True,
            timeout=15,
            cwd=str(search_support_dir()),
            env=env,
            **_SUBPROC_KW,
        )
        if proc.returncode != 0:
            return {
                "available": True,
                "running": False,
                "message": (proc.stderr or proc.stdout or "").strip()[:200],
            }
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        running = False
        state = ""
        for ln in lines:
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            state = str(row.get("State", ""))
            if state.lower() == "running":
                running = True
                break
        return {"available": True, "running": running, "state": state}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"available": True, "running": False, "message": str(exc)}


def start_search() -> tuple[bool, str]:
    ok, msg = ensure_search_support_files()
    if not ok:
        return False, msg
    if not is_docker_installed():
        return False, "Docker not installed"
    ok, msg = ensure_docker_daemon()
    if not ok:
        return False, msg
    cmd = _docker_cmd()
    if not cmd:
        return False, "Search compose file not installed"
    env = docker_cli_env()
    try:
        proc = run_hidden(
            [*cmd, "up", "-d", _SERVICE_NAME],
            capture_output=True,
            timeout=120,
            cwd=str(search_support_dir()),
            env=env,
            **_SUBPROC_KW,
        )
        if proc.returncode == 0:
            return True, "SearXNG container started"
        msg = (proc.stderr or proc.stdout or "docker compose failed").strip()
        return False, msg[:500]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def stop_search() -> tuple[bool, str]:
    ok, msg = ensure_search_support_files()
    if not ok:
        return False, msg
    if not is_docker_installed():
        return False, "Docker not installed"
    ok, msg = ensure_docker_daemon(wait_seconds=15.0)
    if not ok:
        return False, msg
    cmd = _docker_cmd()
    if not cmd:
        return False, "Search compose file not installed"
    env = docker_cli_env()
    try:
        proc = run_hidden(
            [*cmd, "stop", _SERVICE_NAME],
            capture_output=True,
            timeout=60,
            cwd=str(search_support_dir()),
            env=env,
            **_SUBPROC_KW,
        )
        if proc.returncode == 0:
            return True, "SearXNG container stopped"
        msg = (proc.stderr or proc.stdout or "docker compose failed").strip()
        return False, msg[:500]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def update_search_settings(base_url: str, engines: str) -> None:
    settings = load_runtime_settings()
    settings.searxng_base_url = (base_url or "").strip().rstrip("/")
    settings.searxng_engines = (engines or "").strip()
    save_runtime_settings(settings)
