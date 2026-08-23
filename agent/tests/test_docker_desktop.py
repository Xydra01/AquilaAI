"""Docker Desktop discovery helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agent.aquila_runtime import docker_desktop


def test_resolve_docker_executable_windows_path(monkeypatch, tmp_path):
    docker_exe = tmp_path / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
    docker_exe.parent.mkdir(parents=True)
    docker_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "agent.aquila_runtime.docker_desktop.shutil.which",
        lambda _: None,
    )
    monkeypatch.setattr(docker_desktop.os, "name", "nt")
    monkeypatch.setattr(
        docker_desktop,
        "_windows_docker_candidates",
        lambda: [docker_exe],
    )

    assert docker_desktop.resolve_docker_executable() == docker_exe
    assert docker_desktop.is_docker_installed() is True


@patch("agent.aquila_runtime.docker_desktop.resolve_docker_executable", return_value=None)
def test_is_docker_installed_false(mock_resolve):
    assert docker_desktop.is_docker_installed() is False


@patch("agent.aquila_runtime.docker_desktop._docker_version_ok", return_value=(True, "28.0.0"))
@patch(
    "agent.aquila_runtime.docker_desktop.resolve_docker_executable",
    return_value=Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
)
def test_is_docker_daemon_running(mock_resolve, mock_version):
    ok, msg = docker_desktop.is_docker_daemon_running()
    assert ok is True
    assert msg == "28.0.0"
