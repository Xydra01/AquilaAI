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
    _memory_cache.clear()


# Backward compatibility — default instance memory
aquila_memory = get_memory("default")
