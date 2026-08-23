"""Windows subprocess helpers — avoid flashing console windows from the GUI."""
from __future__ import annotations

import os
import subprocess
from typing import Any

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def hidden_creationflags(*, new_process_group: bool = False) -> int:
    if os.name != "nt":
        return 0
    flags = CREATE_NO_WINDOW
    if new_process_group:
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return flags


def run_hidden(
    cmd: list[str] | str,
    *,
    new_process_group: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    flags = hidden_creationflags(new_process_group=new_process_group)
    if flags:
        kwargs.setdefault("creationflags", flags)
    return subprocess.run(cmd, **kwargs)


def popen_hidden(
    cmd: list[str] | str,
    *,
    new_process_group: bool = False,
    **kwargs: Any,
) -> subprocess.Popen:
    flags = hidden_creationflags(new_process_group=new_process_group)
    if flags:
        kwargs.setdefault("creationflags", flags)
    return subprocess.Popen(cmd, **kwargs)
