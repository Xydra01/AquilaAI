"""Persisted runtime configuration for Ollama and SearXNG (desktop + remote)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .workspace_paths import agent_data_path, get_data_root

DEFAULT_STOCK_URL = "http://127.0.0.1:11434"
DEFAULT_TQ_URL = "http://127.0.0.1:11435"
DEFAULT_SEARXNG_URL = "http://127.0.0.1:8080"
DEFAULT_SEARXNG_ENGINES = "google,bing,duckduckgo,wikipedia"

_ENGINE_URLS = {
    "stock": DEFAULT_STOCK_URL,
    "tq": DEFAULT_TQ_URL,
}


def _settings_path() -> Path:
    return agent_data_path("Agent-Instances") / "app_settings.json"


def _env_defaults() -> dict[str, Any]:
    num_ctx_raw = os.getenv("OLLAMA_NUM_CTX", "").strip()
    num_ctx: int | None = None
    if num_ctx_raw.isdigit() and int(num_ctx_raw) > 0:
        num_ctx = int(num_ctx_raw)
    base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_STOCK_URL).strip()
    engine = engine_for_base_url(base_url) or "stock"
    return {
        "ollama_engine": engine,
        "ollama_base_url": base_url,
        "ollama_model": os.getenv("OLLAMA_MODEL", "aquila").strip(),
        "ollama_num_ctx": num_ctx,
        "searxng_base_url": os.getenv("SEARXNG_BASE_URL", DEFAULT_SEARXNG_URL).strip(),
        "searxng_engines": os.getenv(
            "SEARXNG_ENGINES", DEFAULT_SEARXNG_ENGINES
        ).strip(),
    }


@dataclass
class RuntimeSettings:
    ollama_engine: str = "stock"
    ollama_base_url: str = DEFAULT_STOCK_URL
    ollama_model: str = "aquila"
    ollama_num_ctx: int | None = None
    searxng_base_url: str = DEFAULT_SEARXNG_URL
    searxng_engines: str = DEFAULT_SEARXNG_ENGINES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeSettings:
        num_ctx = data.get("ollama_num_ctx")
        if num_ctx is not None and num_ctx != "":
            try:
                num_ctx = int(num_ctx)
                if num_ctx <= 0:
                    num_ctx = None
            except (TypeError, ValueError):
                num_ctx = None
        else:
            num_ctx = None
        return cls(
            ollama_engine=str(data.get("ollama_engine") or "stock"),
            ollama_base_url=str(data.get("ollama_base_url") or DEFAULT_STOCK_URL).strip(),
            ollama_model=str(data.get("ollama_model") or "aquila").strip(),
            ollama_num_ctx=num_ctx,
            searxng_base_url=str(
                data.get("searxng_base_url") or DEFAULT_SEARXNG_URL
            ).strip(),
            searxng_engines=str(
                data.get("searxng_engines") or DEFAULT_SEARXNG_ENGINES
            ).strip(),
        )


def engine_for_base_url(base_url: str) -> str | None:
    normalized = (base_url or "").strip().rstrip("/")
    for engine, url in _ENGINE_URLS.items():
        if normalized == url.rstrip("/"):
            return engine
    return None


def expected_tokens_per_s(
    engine: str | None = None,
    *,
    base_url: str | None = None,
) -> float:
    """Baseline output tokens/s for health checks (stock vs TurboQuant)."""
    eng = (engine or "").strip().lower()
    if not eng and base_url:
        eng = engine_for_base_url(base_url) or ""
    if eng == "tq":
        raw = os.getenv("AQUILA_TQ_EXPECTED_TOKENS_PER_S", "").strip()
        if not raw:
            raw = os.getenv("AQUILA_EXPECTED_TOKENS_PER_S", "30").strip() or "30"
    else:
        raw = os.getenv("AQUILA_EXPECTED_TOKENS_PER_S", "30").strip() or "30"
    try:
        return float(raw)
    except ValueError:
        return 30.0


def engine_base_urls() -> dict[str, str]:
    return dict(_ENGINE_URLS)


def _read_settings_blob() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_runtime_settings() -> RuntimeSettings:
    """Merge env defaults with persisted app_settings.json when present."""
    defaults = _env_defaults()
    saved = _read_settings_blob()
    if saved:
        merged = {**defaults, **saved}
        return RuntimeSettings.from_dict(merged)
    return RuntimeSettings.from_dict(defaults)


def load_app_mcp_servers() -> list[dict[str, Any]]:
    raw = _read_settings_blob().get("mcp_servers")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def save_app_mcp_servers(servers: list[dict[str, Any]]) -> Path:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_settings_blob()
    blob["mcp_servers"] = servers
    if "ollama_engine" not in blob:
        blob.update(load_runtime_settings().to_dict())
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def save_runtime_settings(settings: RuntimeSettings, *, sync_env: bool = True) -> Path:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_settings_blob()
    blob.update(settings.to_dict())
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if sync_env:
        _sync_env_file(settings)
    return path


def set_engine(settings: RuntimeSettings, engine: str) -> RuntimeSettings:
    engine = (engine or "stock").strip().lower()
    if engine in _ENGINE_URLS:
        settings.ollama_engine = engine
        settings.ollama_base_url = _ENGINE_URLS[engine]
    return settings


def active_ollama_config() -> dict[str, Any]:
    s = load_runtime_settings()
    return {
        "engine": s.ollama_engine,
        "base_url": s.ollama_base_url,
        "model": s.ollama_model,
        "num_ctx": s.ollama_num_ctx,
    }


def active_search_config() -> dict[str, str]:
    s = load_runtime_settings()
    return {
        "base_url": s.searxng_base_url.rstrip("/"),
        "engines": s.searxng_engines,
    }


def prefer_model_for_engine(models: list[str], engine: str) -> str | None:
    """Pick a sensible default aquila model for stock vs TQ."""
    if not models:
        return None
    prefs = (
        ["aquila-tq-64k", "aquila-tq-32k", "aquila-tq-96k", "aquila-tq"]
        if engine == "tq"
        else ["aquila_qwopus", "aquila", "aquila_heretic", "aquila-tq"]
    )
    for pref in prefs:
        for tag in models:
            if model_tag_base(tag) == pref:
                return tag
    for pref in prefs:
        for tag in models:
            if pref in model_tag_base(tag):
                return tag
    return models[0]


def model_tag_base(tag: str) -> str:
    return (tag or "").split(":")[0].strip()


def model_tag_matches(requested: str, tag: str) -> bool:
    """True when requested matches a full tag or base name (aquila ~ aquila:latest)."""
    if not requested or not tag:
        return False
    if requested == tag:
        return True
    return model_tag_base(requested) == model_tag_base(tag)


def model_available_on_engine(requested: str, available: list[str]) -> bool:
    return any(model_tag_matches(requested, tag) for tag in available)


def resolve_model_tag(requested: str, available: list[str]) -> str | None:
    """Map saved name to the exact tag Ollama reports."""
    if not available:
        return requested or None
    if requested in available:
        return requested
    for tag in available:
        if model_tag_matches(requested, tag):
            return tag
    return None


def resolve_env_example_path(data_root: Path | None = None) -> Path:
    """Locate``.env.example`` /``.env.EXAMPLE`` under data root or repo."""
    from .workspace_paths import REPO_ROOT

    root = data_root or get_data_root()
    for name in (".env.example", ".env.EXAMPLE"):
        path = root / name
        if path.is_file():
            return path
    for name in (".env.example", ".env.EXAMPLE"):
        path = REPO_ROOT / name
        if path.is_file():
            return path
    return root / ".env.example"


def is_setup_complete() -> bool:
    blob = _read_settings_blob()
    return bool(blob.get("setup_complete"))


def mark_setup_complete() -> Path:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_settings_blob()
    blob["setup_complete"] = True
    if "ollama_engine" not in blob:
        blob.update(load_runtime_settings().to_dict())
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _repo_root() -> Path:
    return get_data_root()


def _env_file_path() -> Path:
    return _repo_root() / ".env"


def _sync_env_file(settings: RuntimeSettings) -> None:
    env_path = _env_file_path()
    if not env_path.is_file():
        return
    updates = {
        "OLLAMA_BASE_URL": settings.ollama_base_url,
        "OLLAMA_MODEL": settings.ollama_model,
        "SEARXNG_BASE_URL": settings.searxng_base_url,
        "SEARXNG_ENGINES": settings.searxng_engines,
    }
    if settings.ollama_num_ctx is not None:
        updates["OLLAMA_NUM_CTX"] = str(settings.ollama_num_ctx)
        
    try:
        from .env_parser import update_env
        update_env(env_path, updates)
    except OSError:
        pass
