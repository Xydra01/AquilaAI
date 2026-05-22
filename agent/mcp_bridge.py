"""MCP server bridge stub for Aquila 4.0 extension (Wave 4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpServerConfig:
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = False


class McpBridge:
    """Placeholder — wire Cursor MCP clients in 4.0."""

    def __init__(self, servers: list[dict[str, Any]] | None = None):
        self.servers = [McpServerConfig(**s) if isinstance(s, dict) else s for s in (servers or [])]

    def list_tools(self) -> list[str]:
        return []

    def call_tool(self, server: str, tool: str, arguments: dict) -> str:
        return f"MCP not configured (server={server}, tool={tool}). Add mcp_servers to instance profile."
