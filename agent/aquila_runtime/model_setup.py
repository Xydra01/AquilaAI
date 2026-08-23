"""First-run model pull/create for packaged Aquila."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from agent.aquila_runtime.subprocess_win import popen_hidden

from agent.aquila_runtime.hardware_profile import HardwareProfile
from agent.aquila_runtime.paths import REPO_ROOT, get_bundled_path, packaged_ollama_binary

ProgressCallback = Callable[[str], None]
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def sanitize_cli_progress(line: str) -> str:
    """Strip terminal control codes from Ollama/docker-style progress output."""
    if not line:
        return ""
    # Progress bars often use carriage returns; keep the latest segment only.
    segment = line.split("\r")[-1]
    cleaned = _ANSI_ESCAPE.sub("", segment)
    return cleaned.strip()


def modelfile_for_profile(profile: HardwareProfile) -> Path:
    return modelfile_by_name(profile.modelfile_name)


def modelfile_by_name(name: str) -> Path:
    bundled = get_bundled_path("modelfiles", name)
    if bundled.is_file():
        return bundled
    repo = REPO_ROOT / "modelfiles" / name
    if repo.is_file():
        return repo
    repo_root = REPO_ROOT / name
    if repo_root.is_file():
        return repo_root
    return bundled


def _ollama_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("NO_COLOR", "1")
    binary = packaged_ollama_binary()
    if binary:
        env["PATH"] = str(binary.parent) + os.pathsep + env.get("PATH", "")
    return env


def _run_ollama(args: list[str], *, on_line: ProgressCallback | None = None) -> tuple[bool, str]:
    from agent.aquila_runtime.ollama_bundle import ensure_packaged_ollama

    ok, msg = ensure_packaged_ollama(on_line)
    if not ok:
        return False, msg
    binary = packaged_ollama_binary()
    if not binary or not binary.is_file():
        return False, "Ollama binary not found after setup"
    cmd = [str(binary), *args]
    try:
        proc = popen_hidden(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(binary.parent),
            env=_ollama_env(),
        )
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if on_line:
                display = sanitize_cli_progress(line)
                if display:
                    on_line(display)
        code = proc.wait()
        if code != 0:
            return False, "\n".join(lines[-20:]) or f"ollama exited {code}"
        return True, "\n".join(lines[-5:])
    except Exception as exc:
        return False, str(exc)


def ensure_recommended_model(
    profile: HardwareProfile,
    *,
    include_heretic: bool = False,
    include_full_model: bool = False,
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """Pull base weights and create the profile's Aquila tag (``aquila`` or ``aquila-lite``)."""

    def progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    pull_tag = profile.pull_tag or "qwen3.5:9b"
    model_tag = profile.default_model or "aquila"

    progress(f"Pulling {pull_tag}...")
    ok, msg = _run_ollama(["pull", pull_tag], on_line=on_progress)
    if not ok:
        return False, f"pull failed: {msg}"

    modelfile = modelfile_for_profile(profile)
    if not modelfile.is_file():
        return False, f"Modelfile not found: {modelfile}"

    progress(f"Creating {model_tag} from {modelfile.name}...")
    ok, msg = _run_ollama(
        ["create", model_tag, "-f", str(modelfile)],
        on_line=on_progress,
    )
    if not ok:
        return False, f"create {model_tag} failed: {msg}"

    if include_full_model and profile.offer_full_model:
        progress("Pulling full Aquila base (qwen3.5:9b)...")
        ok, msg = _run_ollama(["pull", "qwen3.5:9b"], on_line=on_progress)
        if not ok:
            return False, f"full model pull failed: {msg}"
        full_modelfile = modelfile_by_name(profile.full_modelfile_name)
        if not full_modelfile.is_file():
            return False, f"Modelfile not found: {full_modelfile}"
        progress(f"Creating aquila (full) from {full_modelfile.name}...")
        ok, msg = _run_ollama(
            ["create", "aquila", "-f", str(full_modelfile)],
            on_line=on_progress,
        )
        if not ok:
            return False, f"create aquila failed: {msg}"

    if include_heretic and not profile.offer_full_model:
        heretic = get_bundled_path("modelfiles", "Modelfile.Heretic")
        if not heretic.is_file():
            heretic = REPO_ROOT / "Modelfile.Heretic"
        if heretic.is_file():
            progress("Pulling heretic base model...")
            ok, msg = _run_ollama(
                [
                    "pull",
                    "hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M",
                ],
                on_line=on_progress,
            )
            if ok:
                progress("Creating aquila_heretic...")
                _run_ollama(
                    ["create", "aquila_heretic", "-f", str(heretic)],
                    on_line=on_progress,
                )

    label = model_tag.replace("-", " ").title()
    if include_full_model and profile.offer_full_model:
        return True, f"Aquila Lite and full Aquila are ready"
    return True, f"Model {model_tag} ({label}) is ready"


def ensure_optional_model_addons(
    profile: HardwareProfile,
    *,
    include_heretic: bool = False,
    include_full_model: bool = False,
    include_qwopus: bool = False,
    include_stock_aquila: bool = False,
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """Install optional add-on models after the primary profile model is ready."""

    def progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    if include_full_model and profile.offer_full_model:
        progress("Pulling full Aquila base (qwen3.5:9b)...")
        ok, msg = _run_ollama(["pull", "qwen3.5:9b"], on_line=on_progress)
        if not ok:
            return False, f"full model pull failed: {msg}"
        full_modelfile = modelfile_by_name(profile.full_modelfile_name)
        if not full_modelfile.is_file():
            return False, f"Modelfile not found: {full_modelfile}"
        progress(f"Creating aquila (full) from {full_modelfile.name}...")
        ok, msg = _run_ollama(
            ["create", "aquila", "-f", str(full_modelfile)],
            on_line=on_progress,
        )
        if not ok:
            return False, f"create aquila failed: {msg}"
        return True, "Full Aquila (9B) is ready."

    if include_heretic and not profile.offer_full_model:
        heretic = get_bundled_path("modelfiles", "Modelfile.Heretic")
        if not heretic.is_file():
            heretic = REPO_ROOT / "Modelfile.Heretic"
        if not heretic.is_file():
            return False, "Heretic Modelfile not found"
        progress("Pulling heretic base model...")
        ok, msg = _run_ollama(
            [
                "pull",
                "hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M",
            ],
            on_line=on_progress,
        )
        if not ok:
            return False, f"heretic pull failed: {msg}"
        progress("Creating aquila_heretic...")
        ok, msg = _run_ollama(
            ["create", "aquila_heretic", "-f", str(heretic)],
            on_line=on_progress,
        )
        if not ok:
            return False, f"create aquila_heretic failed: {msg}"
        return True, "aquila_heretic is ready."

    if include_qwopus:
        qwopus = modelfile_by_name("Modelfile.Qwopus")
        if not qwopus.is_file():
            return False, "Qwopus Modelfile not found"
        progress("Pulling Qwopus Coder base model...")
        ok, msg = _run_ollama(
            ["pull", "hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Q4_K_M"],
            on_line=on_progress,
        )
        if not ok:
            return False, f"qwopus pull failed: {msg}"
        progress("Creating aquila_qwopus...")
        ok, msg = _run_ollama(
            ["create", "aquila_qwopus", "-f", str(qwopus)],
            on_line=on_progress,
        )
        if not ok:
            return False, f"create aquila_qwopus failed: {msg}"
        return True, "aquila_qwopus is ready."

    if include_stock_aquila:
        stock = modelfile_by_name("Modelfile")
        if not stock.is_file():
            return False, "Stock Aquila Modelfile not found"
        progress("Pulling stock Aquila base (qwen3.5:9b)...")
        ok, msg = _run_ollama(["pull", "qwen3.5:9b"], on_line=on_progress)
        if not ok:
            return False, f"stock aquila pull failed: {msg}"
        progress("Creating aquila (stock qwen3.5:9b)...")
        ok, msg = _run_ollama(
            ["create", "aquila", "-f", str(stock)],
            on_line=on_progress,
        )
        if not ok:
            return False, f"create aquila failed: {msg}"
        return True, "Stock aquila is ready."

    return False, "No optional model selected"
