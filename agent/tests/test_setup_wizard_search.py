"""Setup wizard SearchPage must not crash when Docker is optional."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")


def test_search_page_constructs_when_docker_available_not_running(qapp, monkeypatch):
    from agent.gui.gui_pages.setup_wizard import SearchPage
    from agent.aquila_runtime.virtualization import VirtualizationStatus

    monkeypatch.setattr(
        "agent.gui.gui_pages.setup_wizard.detect_virtualization_status",
        lambda: VirtualizationStatus(enabled=True, message="ok", detail=""),
    )
    monkeypatch.setattr(
        "agent.gui.gui_pages.setup_wizard.docker_status",
        lambda: {"available": True, "running": False, "message": "not running"},
    )
    page = SearchPage()
    assert page.try_docker is not None
    assert page.try_docker.isChecked() is False


def test_search_page_constructs_when_docker_status_raises(qapp, monkeypatch):
    from agent.gui.gui_pages.setup_wizard import SearchPage
    from agent.aquila_runtime.virtualization import VirtualizationStatus

    monkeypatch.setattr(
        "agent.gui.gui_pages.setup_wizard.detect_virtualization_status",
        lambda: VirtualizationStatus(enabled=True, message="ok", detail=""),
    )

    def boom():
        raise RuntimeError("docker probe failed")

    monkeypatch.setattr(
        "agent.gui.gui_pages.setup_wizard.docker_status",
        boom,
    )
    page = SearchPage()
    assert page.try_docker is None


def test_launch_docker_desktop_access_denied_message(monkeypatch):
    from agent.aquila_runtime import docker_desktop as dd

    monkeypatch.setattr(dd, "_docker_desktop_exe", lambda: MagicMock())
    monkeypatch.setattr(dd.os, "name", "nt")

    def raise_denied(*_a, **_k):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(dd.subprocess, "Popen", raise_denied)
    ok, msg = dd.launch_docker_desktop()
    assert ok is False
    assert "Access denied" in msg
    assert "another Windows account" in msg
