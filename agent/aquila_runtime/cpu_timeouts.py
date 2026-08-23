"""CPU-only packaged install tuning (timeouts, thinking, warmup)."""
from __future__ import annotations

import os
import subprocess
import sys

from agent.aquila_runtime.hardware_profile import detect_hardware_profile

_CPU_PROFILES = frozenset({"cpu_only", "snapdragon_arm"})


def is_cpu_limited_profile() -> bool:
    return detect_hardware_profile().id in _CPU_PROFILES


def chat_working_status() -> str:
    if is_cpu_limited_profile():
        return "Working on your message… first reply on CPU can take a few minutes."
    return "Working on your message…"


def chat_loading_status() -> str:
    if is_cpu_limited_profile():
        return (
            "Loading model and generating a reply… "
            "(CPU mode can take several minutes before the first word appears.)"
        )
    return "Loading model and generating a reply…"


def chat_thinking_wait_status() -> str:
    if is_cpu_limited_profile():
        return (
            "Model is generating on CPU — first visible reply can "
            "take several minutes…"
        )
    return "Model is thinking — answer will appear shortly…"


def apply_cpu_friendly_settings() -> bool:
    """Raise inference timeouts and disable native thinking on CPU-bound hosts."""
    if not is_cpu_limited_profile():
        return False
    os.environ["AQUILA_READ_TIMEOUT_MAX"] = "900"
    os.environ["AQUILA_COLD_START_EXTRA_SEC"] = "300"
    os.environ["AQUILA_ENABLE_THINK"] = "0"
    os.environ["AQUILA_ACT_TWO_PHASE"] = "0"
    os.environ.setdefault("AQUILA_KILL_SWITCH_MODE", "wallclock")
    os.environ["AQUILA_WARMUP_ON_START"] = "0"
    os.environ["AQUILA_COMPACT_CHAT"] = "1"
    return True


def inference_read_timeout(*, floor: int = 120) -> int:
    """Seconds for Ollama HTTP read timeout (prefill + generation on CPU can be slow)."""
    base = floor + int(os.getenv("AQUILA_COLD_START_EXTRA_SEC", "90") or "90")
    cap_raw = os.getenv("AQUILA_READ_TIMEOUT_MAX", "").strip()
    if cap_raw.isdigit():
        return max(base, int(cap_raw))
    return base
