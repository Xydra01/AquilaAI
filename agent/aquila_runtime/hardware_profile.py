"""Best-effort hardware detection for packaged Aquila setup presets."""
from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass

from agent.aquila_runtime.subprocess_win import run_hidden

_QWOPUS_PULL = "hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Q4_K_M"
_QWOPUS_MODEL = "aquila_qwopus"
_QWOPUS_MODELFILE = "Modelfile.Qwopus"


@dataclass(frozen=True)
class HardwareProfile:
    id: str
    label: str
    default_model: str = "aquila"
    pull_tag: str = "qwen3.5:9b"
    num_ctx: int = 16384
    performance_note: str = ""
    offer_turboquant: bool = False
    modelfile_name: str = "Modelfile"
    offer_full_model: bool = False
    full_modelfile_name: str = "Modelfile.cpu"


def _gpu_qwopus_profile(**kwargs) -> HardwareProfile:
    """GPU preset: Qwopus Coder as primary, stock aquila optional fallback."""
    return HardwareProfile(
        default_model=_QWOPUS_MODEL,
        pull_tag=_QWOPUS_PULL,
        modelfile_name=_QWOPUS_MODELFILE,
        **kwargs,
    )


def _run_text(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        proc = run_hidden(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except Exception:
        return ""


def _nvidia_vram_mib() -> int | None:
    out = _run_text(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]
    )
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
        m = re.search(r"(\d+)", line)
        if m:
            return int(m.group(1))
    return None


def _windows_processor_name() -> str:
    if os.name != "nt":
        return ""
    out = _run_text(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
        ]
    )
    return out.strip()


def _mac_has_apple_silicon() -> bool:
    if platform.system() != "Darwin":
        return False
    out = _run_text(["sysctl", "-n", "machdep.cpu.brand_string"])
    return "Apple" in out or platform.machine().lower() in ("arm64", "aarch64")


def detect_hardware_profile() -> HardwareProfile:
    machine = platform.machine().lower()
    system = platform.system().lower()

    if os.name == "nt" and machine in ("arm64", "aarch64"):
        return HardwareProfile(
            id="snapdragon_arm",
            label="Windows ARM64 (Copilot+ / Snapdragon)",
            default_model="aquila-lite",
            pull_tag="qwen2.5:3b",
            num_ctx=8192,
            performance_note=(
                "Aquila Lite on CPU (ARM64). Much faster than the 9B model. "
                "Adreno GPU and Hexagon NPU are not used by stock Ollama yet."
            ),
            modelfile_name="Modelfile.lite",
            offer_full_model=True,
            full_modelfile_name="Modelfile.arm",
        )

    vram = _nvidia_vram_mib()
    if vram is not None:
        if vram >= 12_000:
            return _gpu_qwopus_profile(
                id="nvidia_high",
                label=f"NVIDIA GPU ({vram // 1024} GB+ VRAM)",
                num_ctx=32768,
                performance_note=(
                    "Qwopus Coder (agentic/tool-tuned) via Ollama. "
                    "TurboQuant optional in Advanced."
                ),
                offer_turboquant=True,
            )
        if vram >= 6_144:
            return _gpu_qwopus_profile(
                id="nvidia_mid",
                label=f"NVIDIA GPU ({max(1, vram // 1024)} GB VRAM)",
                num_ctx=16384,
                performance_note="Qwopus Coder via GPU-accelerated Ollama.",
            )
        return HardwareProfile(
            id="nvidia_low",
            label=f"NVIDIA GPU ({max(1, vram // 1024)} GB VRAM — low)",
            default_model="aquila-lite",
            pull_tag="qwen2.5:3b",
            num_ctx=8192,
            performance_note=(
                "Aquila Lite fits 4 GB GPUs. Optional full Aquila uses reduced context."
            ),
            modelfile_name="Modelfile.lite",
            offer_full_model=True,
            full_modelfile_name="Modelfile.low-vram",
        )

    if system == "darwin" and _mac_has_apple_silicon():
        return _gpu_qwopus_profile(
            id="apple_metal",
            label="Apple Silicon (Metal)",
            num_ctx=32768,
            performance_note="Qwopus Coder via Metal on macOS.",
        )

    proc = _windows_processor_name().lower()
    if "arc" in proc or "intel" in proc and "graphics" in proc:
        return _gpu_qwopus_profile(
            id="intel_arc",
            label="Intel GPU",
            num_ctx=16384,
            performance_note="Qwopus Coder via Ollama GPU backend when available.",
        )
    if "amd" in proc or "ryzen" in proc:
        return _gpu_qwopus_profile(
            id="amd",
            label="AMD GPU / CPU",
            num_ctx=16384,
        )

    return HardwareProfile(
        id="cpu_only",
        label="CPU",
        default_model="aquila-lite",
        pull_tag="qwen2.5:3b",
        num_ctx=8192,
        performance_note=(
            "Aquila Lite — optimized for CPU-only systems (~2 GB download, "
            "faster replies than the full 9B model)."
        ),
        modelfile_name="Modelfile.lite",
        offer_full_model=True,
        full_modelfile_name="Modelfile.cpu",
    )
