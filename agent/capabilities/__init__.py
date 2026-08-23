"""Aquila capability modules — batched tool orchestration for research."""
from __future__ import annotations

from .base import CapabilityContext, CapabilityResult
from .registry import (
    CAPABILITY_REGISTRY,
    CapabilitySpec,
    get_capability,
    list_capabilities,
    run_capability,
)

__all__ = [
    "CapabilityContext",
    "CapabilityResult",
    "CapabilitySpec",
    "CAPABILITY_REGISTRY",
    "get_capability",
    "list_capabilities",
    "run_capability",
]
