"""SSE ASGI mount for Aquila MCP host on Remote Companion."""
from __future__ import annotations

from typing import Callable


def _extract_bearer(scope: dict) -> str | None:
    from remote import auth

    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    header = headers.get("authorization", "")
    token = auth.extract_bearer(header)
    if token:
        return token
    query = scope.get("query_string", b"").decode("latin-1")
    for part in query.split("&"):
        if part.startswith("token="):
            return part.split("=", 1)[1]
    return None


class McpHostAuthMiddleware:
    """Require paired device token before MCP SSE traffic."""

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            from remote import auth

            token = _extract_bearer(scope)
            if auth.verify_token(token) is None:
                body = b'{"detail":"invalid or missing device token"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


_mcp_sse_app = None


def get_mcp_host_sse_app():
    global _mcp_sse_app
    if _mcp_sse_app is None:
        from mcp.server.transport_security import TransportSecuritySettings

        from agent.core import create_aquila_mcp

        # Device bearer auth is enforced above; disable Host-header rebinding checks
        # so mounts work behind reverse proxies and Starlette TestClient.
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        inner = create_aquila_mcp(transport_security=security).sse_app(mount_path="")
        _mcp_sse_app = McpHostAuthMiddleware(inner)
    return _mcp_sse_app
