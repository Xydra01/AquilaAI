"""Frozen/packaged install path resolution for Aquila."""
from __future__ import annotations

import os
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_DIR.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_mode() -> str:
    """``packaged`` when running from a frozen build; else ``dev``."""
    override = os.getenv("AQUILA_LAUNCH_MODE", "").strip().lower()
    if override in ("dev", "packaged"):
        return override
    return "packaged" if is_frozen() else "dev"


def get_install_root() -> Path:
    """Directory containing the Aquila executable (packaged) or repo root (dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return REPO_ROOT


def get_bundle_root() -> Path:
    """PyInstaller extract dir (``_MEIPASS``) or install root."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return get_install_root()


def get_bundled_path(*parts: str) -> Path:
    """Resolve a path under install/bundle root (e.g. ``modelfiles``, ``runtime/ollama``)."""
    base = get_install_root()
    if not parts:
        return base
    candidates = [base.joinpath(*parts), get_bundle_root().joinpath(*parts)]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def get_default_data_root() -> Path:
    if os.name == "nt":
        local = os.getenv("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / "Aquila"
        return Path.home() / "AppData" / "Local" / "Aquila"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Aquila"
    return Path.home() / ".local" / "share" / "Aquila"


def packaged_ollama_binary() -> Path | None:
    """Portable stock Ollama bundled with a packaged install."""
    suffix = ".exe" if os.name == "nt" else ""
    names = (f"ollama{suffix}",)
    search_dirs = [
        get_bundled_path("runtime", "ollama"),
        get_install_root() / "tools" / "ollama-stock",
        REPO_ROOT / "tools" / "ollama-stock",
    ]
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for name in names:
            direct = directory / name
            if direct.is_file():
                return direct
        for nested in directory.rglob(f"ollama{suffix}"):
            if nested.is_file():
                return nested
    found = __import__("shutil").which("ollama")
    if found:
        return Path(found)
    return None
