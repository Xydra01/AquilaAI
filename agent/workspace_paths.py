"""Canonical filesystem layout for Aquila runtime data (repo root, not agent/)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

AGENT_CORE_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_CORE_DIR.parent

AGENT_DATA_DIR_NAMES = (
    "Agent-Tasks",
    "Agent-Plans",
    "Agent-Research",
    "Agent-Creations",
    "Agent-Drafts",
    "Agent-Logs",
    "Agent-Memory",
    "Agent-Code",
    "Agent-Instances",
)


def get_data_root() -> Path:
    """Repo root for Agent-* data; override with AQUILA_DATA_ROOT for isolated tests."""
    override = os.getenv("AQUILA_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT


def agent_data_path(*parts: str) -> Path:
    """Absolute path under the canonical data root."""
    base = get_data_root()
    if not parts:
        return base
    return base.joinpath(*parts)


def agent_data_rel(*parts: str) -> str:
    """POSIX path relative to data root (e.g. Agent-Tasks/foo.json)."""
    return agent_data_path(*parts).relative_to(get_data_root()).as_posix()


def get_vector_db_path() -> Path:
    return agent_data_path("vector_db")


def ensure_agent_data_dirs() -> None:
    for name in AGENT_DATA_DIR_NAMES:
        agent_data_path(name).mkdir(parents=True, exist_ok=True)
    get_vector_db_path().mkdir(parents=True, exist_ok=True)


def ensure_repo_cwd() -> Path:
    """Process cwd should match data root so legacy relative paths stay consistent."""
    root = get_data_root()
    os.chdir(root)
    return root


def resolve_under_data_root(file_path: str | Path) -> Path:
    """Resolve a workspace-relative or absolute path against the data root."""
    p = Path(file_path)
    if p.is_absolute():
        return p.resolve()
    return (get_data_root() / p).resolve()


def relative_to_data_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(get_data_root()).as_posix()
    except ValueError:
        return path.as_posix()


def migrate_legacy_paths() -> list[str]:
    """
    One-time cleanup: move agent/vector_db and merge stray agent/Agent-* into repo root.
    Skipped under pytest or when AQUILA_DATA_ROOT is set.
    """
    if os.getenv("AQUILA_SKIP_MIGRATE", "").strip().lower() in ("1", "true", "yes"):
        return []
    if os.getenv("AQUILA_DATA_ROOT", "").strip():
        return []
    if "pytest" in sys.modules:
        return []

    actions: list[str] = []
    root = REPO_ROOT
    legacy_vector = AGENT_CORE_DIR / "vector_db"
    canonical_vector = root / "vector_db"

    if legacy_vector.is_dir() and legacy_vector.resolve() != canonical_vector.resolve():
        if not canonical_vector.exists():
            shutil.move(str(legacy_vector), str(canonical_vector))
            actions.append(f"moved {legacy_vector.name} -> {canonical_vector}")
        else:
            for item in legacy_vector.iterdir():
                dest = canonical_vector / item.name
                if dest.exists():
                    continue
                shutil.move(str(item), str(dest))
                actions.append(f"merged vector_db item {item.name}")
            if not any(legacy_vector.iterdir()):
                legacy_vector.rmdir()
                actions.append(f"removed empty {legacy_vector}")

    for name in AGENT_DATA_DIR_NAMES:
        legacy = AGENT_CORE_DIR / name
        if not legacy.is_dir():
            continue
        dest = root / name
        dest.mkdir(parents=True, exist_ok=True)
        for item in legacy.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(legacy)
            target = dest / rel
            if target.exists():
                if target.stat().st_size >= item.stat().st_size:
                    continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            actions.append(f"merged {legacy.name}/{rel.as_posix()}")
        try:
            legacy.rmdir() if legacy.is_dir() and not any(legacy.iterdir()) else None
        except OSError:
            pass
        if legacy.is_dir() and not any(legacy.rglob("*")):
            shutil.rmtree(legacy, ignore_errors=True)
            actions.append(f"removed empty legacy {legacy}")
        elif legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)
            actions.append(f"removed legacy duplicate tree {legacy}")

    return actions
