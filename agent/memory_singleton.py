"""Shared memory instances per Aquila agent instance (3.4)."""
from __future__ import annotations

from memory import DualMemorySystem
from instance_registry import ensure_default_instance

ensure_default_instance()
_memory_cache: dict[str, DualMemorySystem] = {}


def get_memory(instance_id: str = "default") -> DualMemorySystem:
    iid = instance_id or "default"
    if iid not in _memory_cache:
        _memory_cache[iid] = DualMemorySystem(instance_id=iid)
    return _memory_cache[iid]


def get_active_memory() -> DualMemorySystem:
    from instance_registry import get_active_instance_id

    return get_memory(get_active_instance_id())


def reset_memory_cache() -> None:
    for mem in list(_memory_cache.values()):
        try:
            mem.close()
        except Exception:
            pass
    _memory_cache.clear()


class _AquilaMemoryProxy:
    """Always resolve to the current default-instance memory (survives cache resets)."""

    def __init__(self) -> None:
        object.__setattr__(self, "_overrides", {})

    def __getattr__(self, name: str):
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        return getattr(get_memory("default"), name)

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            object.__getattribute__(self, "_overrides")[name] = value

    def __delattr__(self, name: str) -> None:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            del overrides[name]
        else:
            delattr(get_memory("default"), name)


# Backward compatibility — default instance memory
aquila_memory = _AquilaMemoryProxy()
