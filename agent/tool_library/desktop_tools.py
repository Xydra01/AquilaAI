"""Desktop tools for native OS interactions (e.g. launching applications)."""
from __future__ import annotations

import os
import subprocess
import platform
from typing import Any

from agent.core import format_tool_result


def open_application(app_name_or_path: str) -> str:
    """
    Open a local application or file using the native OS handler.
    USE WHEN: You need to launch an external GUI app (like a browser or calendar) on the host machine.
    """
    system = platform.system()
    try:
        if system == "Windows":
            # os.startfile is only available on Windows
            os.startfile(app_name_or_path)
        elif system == "Darwin":
            subprocess.Popen(["open", app_name_or_path])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", app_name_or_path])
        else:
            return format_tool_result("ERROR", "open_application failed", f"Unsupported OS: {system}")
            
        return format_tool_result("OK", "open_application", f"Launched: {app_name_or_path}")
    except Exception as e:
        return format_tool_result("ERROR", "open_application failed", str(e))


DESKTOP_TOOLS: dict[str, dict[str, Any]] = {
    "open_application": {
        "func": open_application,
        "description": "Open a local application or file using the native OS handler.",
    },
}
