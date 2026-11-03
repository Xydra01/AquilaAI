"""Tool catalog and JSON schema for Phase 1 code agent loop."""
from __future__ import annotations

import os

from agent.parser.structured_schema import build_agent_action_json_schema
from agent.tool_library.code_agent_tools import CODE_AGENT_TOOL_REGISTRY

_BASE_CODE_AGENT_TOOLS = frozenset(
    k for k in CODE_AGENT_TOOL_REGISTRY if k != "semantic_search"
)
CODE_AGENT_TOOLS = _BASE_CODE_AGENT_TOOLS


def _semantic_search_enabled() -> bool:
    return os.getenv("AQUILA_CODE_SEMANTIC_SEARCH", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def get_active_code_agent_tools() -> frozenset[str]:
    """Return tool names available for the current session (env-gated semantic_search)."""
    if _semantic_search_enabled():
        return _BASE_CODE_AGENT_TOOLS | {"semantic_search"}
    return _BASE_CODE_AGENT_TOOLS


def get_code_tool_registry() -> dict[str, dict]:
    """Return tool name → {func, description} for active code mode tools."""
    active = get_active_code_agent_tools()
    return {k: v for k, v in CODE_AGENT_TOOL_REGISTRY.items() if k in active}


def build_code_agent_json_schema(tool_names: frozenset[str] | None = None) -> dict:
    """Ollama strict schema: one tool per turn."""
    names = tool_names or get_active_code_agent_tools()
    registry = {k: CODE_AGENT_TOOL_REGISTRY[k] for k in names if k in CODE_AGENT_TOOL_REGISTRY}
    return build_agent_action_json_schema(
        names,
        registry,
        simplify=True,
        max_tools_per_turn=1,
        require_final_report=False,
    )


def format_code_tool_docs(tool_names: frozenset[str] | None = None) -> str:
    """Short tool list for system prompt."""
    names = tool_names or get_active_code_agent_tools()
    registry = get_code_tool_registry()
    lines = []
    for name in sorted(names):
        desc = (registry[name].get("description") or "").split("\n")[0]
        lines.append(f"- `{name}` — {desc}")
    return "\n".join(lines)
