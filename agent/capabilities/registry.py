"""Capability registry: IDs, schemas, and dispatch."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from pydantic import BaseModel

from .base import CapabilityContext, CapabilityHandler, CapabilityResult


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    version: str
    title: str
    description: str
    input_model: Type[BaseModel]
    handler: CapabilityHandler
    tier: str = "A"
    modes: frozenset[str] = frozenset({"research"})


_REGISTRY: dict[str, CapabilitySpec] = {}


def register_capability(spec: CapabilitySpec) -> None:
    _REGISTRY[spec.capability_id] = spec


def get_capability(capability_id: str) -> CapabilitySpec | None:
    return _REGISTRY.get(capability_id)


def list_capabilities(*, mode: str | None = None) -> list[CapabilitySpec]:
    specs = list(_REGISTRY.values())
    if mode:
        mode_norm = mode.strip().lower()
        specs = [s for s in specs if mode_norm in s.modes or not s.modes]
    return sorted(specs, key=lambda s: s.capability_id)


def run_capability(
    capability_id: str,
    ctx: CapabilityContext,
    arguments: dict[str, Any] | None = None,
) -> CapabilityResult:
    spec = get_capability(capability_id)
    if spec is None:
        return CapabilityResult.failure("unknown_capability", f"Unknown capability: {capability_id}")
    try:
        validated = spec.input_model.model_validate(arguments or {})
    except Exception as exc:
        return CapabilityResult.failure("invalid_input", str(exc))
    try:
        return spec.handler(ctx, validated)
    except Exception as exc:
        return CapabilityResult.failure("runtime_error", str(exc))


def capability_input_schema(capability_id: str) -> dict[str, Any] | None:
    spec = get_capability(capability_id)
    if spec is None:
        return None
    return spec.input_model.model_json_schema()


def prepare_capability_input_schema(cap_id: str) -> dict[str, Any] | None:
    """Re-export for callers that prepare per-cap Ollama argument schemas."""
    from agent.parser.structured_schema import prepare_capability_input_schema as _prepare

    return _prepare(cap_id)


def _register_all() -> None:
    """Import capability modules to populate registry."""
    from . import dev  # noqa: F401
    from . import learn  # noqa: F401
    from . import persona  # noqa: F401
    from . import planning  # noqa: F401
    from . import research  # noqa: F401
    from . import web  # noqa: F401
    from . import writing  # noqa: F401


_register_all()

CAPABILITY_REGISTRY = _REGISTRY
