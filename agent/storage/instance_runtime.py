"""Apply runtime settings and per-instance Ollama overrides before a run."""
from __future__ import annotations

from typing import Optional


def apply_instance_for_run(instance_id: Optional[str] = None) -> str:
    """Configure global Ollama client for instance_id; return effective id."""
    import main as brain

    try:
        brain.apply_runtime_settings(brain.client)
    except Exception:
        pass

    effective = instance_id
    try:
        from .instance_registry import get_active_instance_id, get_instance, set_active_instance_id
    except ImportError:
        return effective or "default"

    if not effective:
        try:
            effective = get_active_instance_id()
        except Exception:
            effective = "default"

    if effective:
        try:
            set_active_instance_id(effective)
        except Exception:
            pass

    profile = get_instance(effective) if effective else None
    if profile is not None and getattr(profile, "ollama_base_url", None):
        brain.client.configure(base_url=profile.ollama_base_url.strip())
    if profile is not None and getattr(profile, "ollama_model", None):
        brain.client.configure(model_name=profile.ollama_model.strip())
    return effective or "default"
