"""Ship and install optional SearXNG Docker files for packaged Aquila."""
from __future__ import annotations

import shutil
from pathlib import Path

from agent.aquila_runtime.paths import get_bundled_path
from agent.storage.workspace_paths import REPO_ROOT, get_data_root

_SEARCH_FILES = ("docker-compose.yml", "searxng-settings.yml")


def search_support_dir() -> Path:
    return get_data_root()


def _bundled_search_file(name: str) -> Path | None:
    bundled = get_bundled_path("search", name)
    if bundled.is_file():
        return bundled
    repo = REPO_ROOT / name
    if repo.is_file():
        return repo
    return None


def ensure_search_support_files() -> tuple[bool, str]:
    """Copy docker-compose + searxng settings into the user data folder if missing."""
    root = search_support_dir()
    root.mkdir(parents=True, exist_ok=True)

    missing = [name for name in _SEARCH_FILES if not (root / name).is_file()]
    if not missing:
        return True, str(root / "docker-compose.yml")

    copied: list[str] = []
    for name in missing:
        src = _bundled_search_file(name)
        if not src:
            return (
                False,
                f"Missing {name} in install bundle. Web search is optional — skip Docker setup.",
            )
        dest = root / name
        shutil.copy2(src, dest)
        copied.append(name)

    return True, f"Installed search files: {', '.join(copied)}"
