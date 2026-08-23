"""CPU virtualization firmware checks (Docker / WSL2 prerequisites on Windows)."""
from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass

from agent.aquila_runtime.subprocess_win import run_hidden

_BIOS_HELP = (
    "Enable Intel VT-x or AMD-V in your BIOS/UEFI firmware settings, then reboot. "
    "In Task Manager → Performance → CPU, look for “Virtualization: Enabled”."
)


@dataclass(frozen=True)
class VirtualizationStatus:
    enabled: bool | None
    message: str
    detail: str = ""


def _windows_firmware_enabled() -> bool | None:
    """Return True/False from firmware flag, or None if the check could not run."""
    script = (
        "$p = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue "
        "| Select-Object -First 1; "
        "if ($null -eq $p) { exit 2 }; "
        "if ($p.VirtualizationFirmwareEnabled) { 'true' } else { 'false' }"
    )
    try:
        proc = run_hidden(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 2:
        return None
    raw = (proc.stdout or "").strip().lower()
    if raw in ("true", "1"):
        return True
    if raw in ("false", "0"):
        return False
    return None


def _virtualization_likely_enabled() -> bool | None:
    """Heuristic when WMI firmware query is inconclusive."""
    if os.name != "nt":
        return None
    try:
        from agent.aquila_runtime.docker_desktop import is_docker_installed

        if is_docker_installed():
            return True
    except Exception:
        pass
    return None


def detect_virtualization_status() -> VirtualizationStatus:
    """Best-effort firmware virtualization check (Windows only)."""
    if os.name != "nt":
        return VirtualizationStatus(
            enabled=None,
            message="Virtualization check is only available on Windows.",
        )

    enabled = _windows_firmware_enabled()
    if enabled is None:
        enabled = _virtualization_likely_enabled()
    if enabled is True:
        return VirtualizationStatus(
            enabled=True,
            message="CPU virtualization is enabled.",
        )
    if enabled is False:
        return VirtualizationStatus(
            enabled=False,
            message="CPU virtualization is disabled in firmware.",
            detail=_BIOS_HELP,
        )
    return VirtualizationStatus(
        enabled=None,
        message="Could not determine whether CPU virtualization is enabled.",
        detail=_BIOS_HELP,
    )


def docker_prerequisites_ok() -> tuple[bool, str]:
    """Whether Docker Desktop is likely to work on this host."""
    if platform.system().lower() != "windows":
        return True, "ok"
    status = detect_virtualization_status()
    if status.enabled is False:
        return False, (
            f"{status.message} Docker Desktop requires virtualization. "
            f"{status.detail}"
        )
    return True, status.message
