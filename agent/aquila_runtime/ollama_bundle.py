"""Download or locate the portable Ollama binary for packaged installs."""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from agent.aquila_runtime.paths import get_install_root, is_frozen, packaged_ollama_binary

ProgressCallback = Callable[[str], None]

PACKAGED_OLLAMA_VERSION = os.getenv("AQUILA_OLLAMA_VERSION", "v0.31.1").strip() or "v0.31.1"
_GITHUB_BASE = "https://github.com/ollama/ollama/releases/download"


def ollama_install_dir() -> Path:
    return get_install_root() / "runtime" / "ollama"


def _host_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return "amd64"


def _release_asset() -> tuple[str, str]:
    """Return (filename, archive_kind) for the current OS."""
    arch = _host_arch()
    if os.name == "nt":
        name = "ollama-windows-arm64.zip" if arch == "arm64" else "ollama-windows-amd64.zip"
        return name, "zip"
    if sys.platform == "darwin":
        return "ollama-darwin.tgz", "tgz"
    return f"ollama-linux-{arch}.tgz", "tgz"


def _find_binary_in(directory: Path) -> Path | None:
    suffix = ".exe" if os.name == "nt" else ""
    direct = directory / f"ollama{suffix}"
    if direct.is_file():
        return direct
    for nested in directory.rglob(f"ollama{suffix}"):
        if nested.is_file():
            return nested
    return None


def _download(url: str, dest: Path, on_progress: ProgressCallback | None) -> None:
    if on_progress:
        on_progress(f"Downloading {url.split('/')[-1]}…")

    def report(block_num: int, block_size: int, total_size: int) -> None:
        if not on_progress or total_size <= 0:
            return
        done = min(block_num * block_size, total_size)
        pct = int(done * 100 / total_size)
        if block_num % 50 == 0:
            on_progress(f"Downloading Ollama… {pct}%")

    urllib.request.urlretrieve(url, dest, reporthook=report)


def _extract_archive(archive: Path, dest: Path, kind: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        return
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(dest, filter="data")


def ensure_packaged_ollama(
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """Ensure a portable Ollama binary exists for packaged installs."""

    def progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    existing = packaged_ollama_binary()
    if existing and existing.is_file():
        return True, f"Ollama ready at {existing}"

    if not is_frozen():
        if existing:
            return True, str(existing)
        return False, (
            "Ollama binary not found. Install Ollama locally or run from a dev checkout "
            "with tools/ollama-stock."
        )

    dest_dir = ollama_install_dir()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Cannot create {dest_dir}: {exc}"

    asset, kind = _release_asset()
    url = f"{_GITHUB_BASE}/{PACKAGED_OLLAMA_VERSION}/{asset}"
    progress(f"Ollama not bundled — fetching {PACKAGED_OLLAMA_VERSION}…")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset
        try:
            _download(url, archive, on_progress)
        except urllib.error.URLError as exc:
            return False, f"Download failed: {exc}"
        except OSError as exc:
            return False, f"Download failed: {exc}"

        progress("Extracting Ollama…")
        try:
            _extract_archive(archive, dest_dir, kind)
        except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
            return False, f"Extract failed: {exc}"

    binary = _find_binary_in(dest_dir)
    if not binary:
        return False, f"Ollama binary missing after extract in {dest_dir}"

    if os.name != "nt":
        binary.chmod(binary.stat().st_mode | 0o111)

    progress("Ollama installed.")
    return True, str(binary)


def copy_dev_ollama_into_bundle(source: Path, dest_dir: Path | None = None) -> Path | None:
    """Copy a local ollama binary into the install tree (build-time helper)."""
    if not source.is_file():
        return None
    target_dir = dest_dir or ollama_install_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix
    target = target_dir / f"ollama{suffix}"
    shutil.copy2(source, target)
    if os.name != "nt":
        target.chmod(target.stat().st_mode | 0o111)
    return target
