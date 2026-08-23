"""Virtualization detection helpers."""
from __future__ import annotations

from unittest.mock import patch

from agent.aquila_runtime import virtualization


@patch(
    "agent.aquila_runtime.docker_desktop.is_docker_installed",
    return_value=True,
)
@patch(
    "agent.aquila_runtime.virtualization._windows_firmware_enabled",
    return_value=None,
)
def test_virtualization_assumes_enabled_when_docker_present(mock_fw, mock_docker):
    status = virtualization.detect_virtualization_status()
    assert status.enabled is True


@patch(
    "agent.aquila_runtime.docker_desktop.is_docker_installed",
    return_value=False,
)
@patch(
    "agent.aquila_runtime.virtualization._windows_firmware_enabled",
    return_value=False,
)
def test_detect_virtualization_disabled(mock_fw, mock_docker):
    status = virtualization.detect_virtualization_status()
    assert status.enabled is False
    assert "disabled" in status.message.lower()


@patch(
    "agent.aquila_runtime.virtualization._windows_firmware_enabled",
    return_value=True,
)
def test_docker_prerequisites_ok_when_enabled(mock_fw):
    ok, msg = virtualization.docker_prerequisites_ok()
    assert ok is True
    assert msg
