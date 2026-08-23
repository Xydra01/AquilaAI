"""Setup health checklist for Settings / first-run wizard."""
from __future__ import annotations

from agent.core import client
from agent.aquila_runtime.hardware_profile import detect_hardware_profile
from agent.remote import server_control
from agent.research import docker_status, probe_health
from agent.storage import load_runtime_settings, model_available_on_engine


def collect_setup_health() -> dict:
    settings = load_runtime_settings()
    profile = detect_hardware_profile()
    engines = server_control.engine_status()
    stock_up = any(e.get("up") for e in engines if e.get("engine") == "stock")
    models_detail = client.discover_aquila_models(
        primary_base_url=settings.ollama_base_url
    )
    models = models_detail.get("models") or []
    model_ok = model_available_on_engine(settings.ollama_model, models)
    search_ok, search_msg = probe_health()
    docker = docker_status()

    return {
        "profile": profile,
        "ollama_running": stock_up,
        "model_ready": model_ok and bool(models),
        "model_message": models_detail.get("error") or (
            f"{len(models)} aquila model(s)" if models else "No aquila models"
        ),
        "search_ok": search_ok,
        "search_message": search_msg,
        "docker_available": bool(docker.get("available")),
        "docker_running": bool(docker.get("running")),
        "docker_message": docker.get("message") or docker.get("state") or "",
    }
