"""Hardware profile detection tests."""
from __future__ import annotations

import pytest

from agent.aquila_runtime.hardware_profile import HardwareProfile, detect_hardware_profile


def test_snapdragon_arm_profile(monkeypatch):
    monkeypatch.setattr("agent.aquila_runtime.hardware_profile.os.name", "nt")
    monkeypatch.setattr("agent.aquila_runtime.hardware_profile.platform.machine", lambda: "ARM64")
    monkeypatch.setattr(
        "agent.aquila_runtime.hardware_profile._nvidia_vram_mib",
        lambda: None,
    )
    prof = detect_hardware_profile()
    assert prof.id == "snapdragon_arm"
    assert prof.default_model == "aquila-lite"
    assert prof.pull_tag == "qwen2.5:3b"
    assert prof.num_ctx == 8192


def test_nvidia_high_profile(monkeypatch):
    monkeypatch.setattr(
        "agent.aquila_runtime.hardware_profile._nvidia_vram_mib",
        lambda: 16_384,
    )
    prof = detect_hardware_profile()
    assert prof.id == "nvidia_high"
    assert prof.offer_turboquant is True


def test_nvidia_low_profile(monkeypatch):
    monkeypatch.setattr(
        "agent.aquila_runtime.hardware_profile._nvidia_vram_mib",
        lambda: 4096,
    )
    prof = detect_hardware_profile()
    assert prof.id == "nvidia_low"
    assert prof.default_model == "aquila-lite"
    assert prof.pull_tag == "qwen2.5:3b"
    assert prof.num_ctx == 8192
    assert prof.offer_full_model is True
    assert prof.full_modelfile_name == "Modelfile.low-vram"


def test_nvidia_mid_profile_8gb(monkeypatch):
    monkeypatch.setattr(
        "agent.aquila_runtime.hardware_profile._nvidia_vram_mib",
        lambda: 8192,
    )
    prof = detect_hardware_profile()
    assert prof.id == "nvidia_mid"
    assert prof.default_model == "aquila_qwopus"
    assert prof.pull_tag == "hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Q4_K_M"
    assert prof.modelfile_name == "Modelfile.Qwopus"
    assert prof.num_ctx == 16384
    assert prof.offer_full_model is False


def test_nvidia_mid_profile_6gb_boundary(monkeypatch):
    monkeypatch.setattr(
        "agent.aquila_runtime.hardware_profile._nvidia_vram_mib",
        lambda: 6144,
    )
    prof = detect_hardware_profile()
    assert prof.id == "nvidia_mid"
    assert prof.default_model == "aquila_qwopus"


def test_modelfile_lite_exists():
    from agent.aquila_runtime.paths import REPO_ROOT

    path = REPO_ROOT / "modelfiles" / "Modelfile.lite"
    assert path.is_file()


def test_modelfile_qwopus_exists():
    from agent.aquila_runtime.paths import REPO_ROOT

    path = REPO_ROOT / "modelfiles" / "Modelfile.Qwopus"
    assert path.is_file()
