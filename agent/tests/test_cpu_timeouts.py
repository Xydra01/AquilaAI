"""CPU timeout helpers."""
from __future__ import annotations

from agent.aquila_runtime.cpu_timeouts import (
    apply_cpu_friendly_settings,
    chat_loading_status,
    chat_thinking_wait_status,
    chat_working_status,
    inference_read_timeout,
    is_cpu_limited_profile,
)


def test_apply_cpu_friendly_settings_for_cpu_profile(monkeypatch):
    import os

    monkeypatch.delenv("AQUILA_READ_TIMEOUT_MAX", raising=False)
    monkeypatch.delenv("AQUILA_COLD_START_EXTRA_SEC", raising=False)
    monkeypatch.delenv("AQUILA_ENABLE_THINK", raising=False)

    class _Prof:
        id = "cpu_only"

    monkeypatch.setattr(
        "agent.aquila_runtime.cpu_timeouts.detect_hardware_profile",
        lambda: _Prof(),
    )
    assert apply_cpu_friendly_settings() is True
    assert os.environ["AQUILA_READ_TIMEOUT_MAX"] == "900"
    assert os.environ["AQUILA_COLD_START_EXTRA_SEC"] == "300"
    assert os.environ["AQUILA_ENABLE_THINK"] == "0"
    assert os.environ["AQUILA_ACT_TWO_PHASE"] == "0"
    assert os.environ["AQUILA_WARMUP_ON_START"] == "0"
    assert os.environ["AQUILA_COMPACT_CHAT"] == "1"


def test_inference_read_timeout_uses_cap(monkeypatch):
    monkeypatch.setenv("AQUILA_COLD_START_EXTRA_SEC", "300")
    monkeypatch.setenv("AQUILA_READ_TIMEOUT_MAX", "900")
    assert inference_read_timeout(floor=120) == 900


def test_chat_status_messages_cpu(monkeypatch):
    class _Prof:
        id = "cpu_only"

    monkeypatch.setattr(
        "agent.aquila_runtime.cpu_timeouts.detect_hardware_profile",
        lambda: _Prof(),
    )
    assert "CPU" in chat_working_status()
    assert "CPU" in chat_loading_status()
    assert "CPU" in chat_thinking_wait_status()


def test_chat_status_messages_gpu(monkeypatch):
    class _Prof:
        id = "nvidia_high"

    monkeypatch.setattr(
        "agent.aquila_runtime.cpu_timeouts.detect_hardware_profile",
        lambda: _Prof(),
    )
    assert "CPU" not in chat_working_status()
    assert "CPU" not in chat_loading_status()
    assert "CPU" not in chat_thinking_wait_status()
    assert is_cpu_limited_profile() is False
