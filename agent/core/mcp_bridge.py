"""MCP server bridge — stdio and SSE transports for Aquila 4.0."""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Callable

_MCP_IMPORT_ERROR: str | None = None
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    _MCP_AVAILABLE = True
except ImportError as exc:
    ClientSession = None  # type: ignore[misc, assignment]
    _MCP_AVAILABLE = False
    _MCP_IMPORT_ERROR = str(exc)


def mcp_available() -> bool:
    return _MCP_AVAILABLE


def mcp_tool_id(server: str, tool: str) -> str:
    safe_server = re.sub(r"[^a-zA-Z0-9_]+", "_", (server or "server").strip())[:48]
    safe_tool = re.sub(r"[^a-zA-Z0-9_]+", "_", (tool or "tool").strip())[:64]
    return f"mcp__{safe_server}__{safe_tool}"


def parse_mcp_tool_id(tool_id: str) -> tuple[str, str] | None:
    if not tool_id or not tool_id.startswith("mcp__"):
        return None
    parts = tool_id.split("__", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def mcp_allowed_for_mode(mode: str) -> bool:
    raw = os.getenv(
        "AQUILA_MCP_ALLOWED_MODES",
        "autonomous,task,research,code,writing",
    )
    allowed = {m.strip().lower() for m in raw.split(",") if m.strip()}
    mode_norm = (mode or "").strip().lower()
    if mode_norm in ("autonomous", "task"):
        return "autonomous" in allowed or "task" in allowed
    return mode_norm in allowed


@dataclass
class McpServerConfig:
    name: str
    transport: str = "stdio"  # stdio | sse
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    enabled: bool = False
    allowed_modes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpServerConfig:
        if not isinstance(data, dict):
            return cls(name="unknown")
        return cls(
            name=str(data.get("name") or "server"),
            transport=str(data.get("transport") or "stdio").lower(),
            command=str(data.get("command") or ""),
            args=list(data.get("args") or []),
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
            url=str(data.get("url") or ""),
            enabled=bool(data.get("enabled")),
            allowed_modes=list(data.get("allowed_modes") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "url": self.url,
            "enabled": self.enabled,
            "allowed_modes": list(self.allowed_modes),
        }


@dataclass
class McpToolDescriptor:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]
    aquila_name: str

    def to_tool_meta(self, call_fn: Callable[..., str]) -> dict[str, Any]:
        return {
            "func": call_fn,
            "description": f"[MCP:{self.server}] {self.description}".strip(),
            "input_schema": self.input_schema,
            "_mcp_server": self.server,
            "_mcp_tool": self.name,
        }


class _AsyncLoopRunner:
    """Background asyncio loop for MCP client sessions."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._ready.clear()
        self._thread = threading.Thread(target=_run, name="mcp-bridge", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def run(self, coro, *, timeout: float = 120.0):
        self.start()
        if not self._loop:
            raise RuntimeError("MCP async loop failed to start")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def stop(self) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3)
        self._loop = None
        self._thread = None


@dataclass
class _ServerState:
    config: McpServerConfig
    healthy: bool = False
    error: str = ""
    tools: list[McpToolDescriptor] = field(default_factory=list)
    stack: Any = None
    session: Any = None


class McpBridge:
    """Connect to configured MCP servers and expose tools to Aquila."""

    def __init__(self, servers: list[dict[str, Any] | McpServerConfig] | None = None):
        parsed: list[McpServerConfig] = []
        for item in servers or []:
            if isinstance(item, McpServerConfig):
                parsed.append(item)
            elif isinstance(item, dict):
                parsed.append(McpServerConfig.from_dict(item))
        self.servers = parsed
        self._runner = _AsyncLoopRunner()
        self._states: dict[str, _ServerState] = {}
        self._tool_index: dict[str, McpToolDescriptor] = {}

    @classmethod
    def from_sources(
        cls,
        *,
        app_settings: list[dict[str, Any]] | None = None,
        instance_servers: list[dict[str, Any]] | None = None,
    ) -> McpBridge:
        merged: dict[str, McpServerConfig] = {}
        for raw in app_settings or []:
            cfg = McpServerConfig.from_dict(raw)
            if cfg.name:
                merged[cfg.name] = cfg
        for raw in instance_servers or []:
            cfg = McpServerConfig.from_dict(raw)
            if cfg.name:
                merged[cfg.name] = cfg
        return cls(list(merged.values()))

    def enabled_servers(self) -> list[McpServerConfig]:
        return [s for s in self.servers if s.enabled]

    def _connect_timeout_seconds(self) -> float:
        raw = os.getenv("AQUILA_MCP_CONNECT_TIMEOUT", "").strip()
        if raw:
            try:
                return max(3.0, float(raw))
            except ValueError:
                pass
        try:
            from agent.aquila_runtime.paths import is_frozen

            return 15.0 if is_frozen() else 60.0
        except Exception:
            return 30.0

    def connect_all(self) -> dict[str, str]:
        """Connect enabled servers. Returns {server_name: status_message}."""
        if not _MCP_AVAILABLE:
            msg = _MCP_IMPORT_ERROR or "mcp package not installed"
            return {s.name: f"error: {msg}" for s in self.enabled_servers()}
        statuses: dict[str, str] = {}
        timeout = self._connect_timeout_seconds()
        for cfg in self.enabled_servers():
            try:
                self._runner.run(self._connect_server(cfg), timeout=timeout)
                st = self._states.get(cfg.name)
                statuses[cfg.name] = "ok" if st and st.healthy else (st.error if st else "error")
            except Exception as exc:
                statuses[cfg.name] = f"error: {exc}"
        self._rebuild_tool_index()
        return statuses

    def disconnect_all(self) -> None:
        if not _MCP_AVAILABLE:
            self._states.clear()
            self._tool_index.clear()
            return
        try:
            self._runner.run(self._disconnect_all_async(), timeout=30)
        except Exception:
            pass
        self._states.clear()
        self._tool_index.clear()
        self._runner.stop()

    async def _disconnect_all_async(self) -> None:
        for name in list(self._states.keys()):
            await self._disconnect_server(name)

    async def _disconnect_server(self, name: str) -> None:
        st = self._states.pop(name, None)
        if not st or not st.stack:
            return
        try:
            await st.stack.aclose()
        except Exception:
            pass

    async def _connect_server(self, cfg: McpServerConfig) -> None:
        await self._disconnect_server(cfg.name)
        st = _ServerState(config=cfg)
        self._states[cfg.name] = st
        if not _MCP_AVAILABLE:
            st.error = _MCP_IMPORT_ERROR or "mcp not installed"
            return
        stack = AsyncExitStack()
        try:
            if cfg.transport == "sse":
                if not cfg.url.strip():
                    raise ValueError("SSE transport requires url")
                read, write = await stack.enter_async_context(sse_client(cfg.url.strip()))
            else:
                if not cfg.command.strip():
                    raise ValueError("stdio transport requires command")
                params = StdioServerParameters(
                    command=cfg.command.strip(),
                    args=list(cfg.args),
                    env=cfg.env or None,
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            st.session = session
            st.stack = stack
            st.healthy = True
            for tool in listed.tools:
                desc = McpToolDescriptor(
                    server=cfg.name,
                    name=tool.name,
                    description=str(tool.description or tool.name),
                    input_schema=dict(tool.inputSchema or {"type": "object", "properties": {}}),
                    aquila_name=mcp_tool_id(cfg.name, tool.name),
                )
                st.tools.append(desc)
        except Exception as exc:
            st.error = str(exc)
            st.healthy = False
            try:
                await stack.aclose()
            except Exception:
                pass

    def _rebuild_tool_index(self) -> None:
        self._tool_index.clear()
        for st in self._states.values():
            if not st.healthy:
                continue
            for desc in st.tools:
                self._tool_index[desc.aquila_name] = desc

    def list_tools(self) -> list[McpToolDescriptor]:
        return list(self._tool_index.values())

    def list_tool_names(self) -> list[str]:
        return list(self._tool_index.keys())

    def server_health(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for cfg in self.servers:
            st = self._states.get(cfg.name)
            out[cfg.name] = {
                "enabled": cfg.enabled,
                "transport": cfg.transport,
                "healthy": bool(st and st.healthy),
                "error": st.error if st else "",
                "tool_count": len(st.tools) if st and st.healthy else 0,
            }
        return out

    def test_server(self, name: str) -> dict[str, Any]:
        cfg = next((s for s in self.servers if s.name == name), None)
        if not cfg:
            return {"ok": False, "error": f"Unknown server {name!r}"}
        prev = cfg.enabled
        cfg.enabled = True
        try:
            status = self.connect_all().get(name, "error")
            health = self.server_health().get(name, {})
            return {"ok": health.get("healthy"), "status": status, **health}
        finally:
            cfg.enabled = prev

    def call_tool(self, server: str, tool: str, arguments: dict | None = None) -> str:
        if not _MCP_AVAILABLE:
            return f"❌ MCP not available: {_MCP_IMPORT_ERROR or 'install mcp package'}"
        st = self._states.get(server)
        if not st or not st.healthy or not st.session:
            return f"❌ MCP server {server!r} not connected ({st.error if st else 'missing'})"
        args = arguments or {}

        async def _call() -> str:
            result = await st.session.call_tool(tool, args)
            parts: list[str] = []
            for block in result.content:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
                else:
                    parts.append(str(block))
            if parts:
                return "\n".join(parts)
            if result.isError:
                return f"❌ MCP tool error: {tool}"
            return "(Success)"

        try:
            return self._runner.run(_call(), timeout=120)
        except Exception as exc:
            return f"❌ MCP call failed: {exc}"

    def build_tool_registry(self) -> dict[str, dict[str, Any]]:
        """Return Aquila-style tool entries for enabled MCP tools."""
        registry: dict[str, dict[str, Any]] = {}
        for desc in self.list_tools():
            server, tool = desc.server, desc.name

            def _make_fn(s: str, t: str) -> Callable[..., str]:
                def _fn(**kwargs: Any) -> str:
                    return self.call_tool(s, t, kwargs)

                return _fn

            registry[desc.aquila_name] = desc.to_tool_meta(_make_fn(server, tool))
        return registry


def load_mcp_servers_from_settings() -> list[dict[str, Any]]:
    try:
        from agent.storage import load_app_mcp_servers

        return load_app_mcp_servers()
    except ImportError:
        return []


def merge_tools_with_mcp(base: dict, bridge: McpBridge | None) -> dict:
    if not bridge:
        return dict(base)
    merged = dict(base)
    merged.update(bridge.build_tool_registry())
    return merged
