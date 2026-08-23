# MCP Integration (Aquila 3.5+)

Aquila supports MCP in **two directions**:

| Direction | Module | Purpose |
|-----------|--------|---------|
| **Client** (Aquila calls external MCP) | [`mcp_bridge.py`](../agent/core/mcp_bridge.py) | MongoDB, GitHub, custom servers as `mcp__*` tools inside Aquila loops |
| **Host** (Cursor calls Aquila) | [`mcp_host.py`](../agent/core/mcp_host.py) | Six meta-tools for parallel Cursor + local Ollama work — see [aquila-mcp-host.md](aquila-mcp-host.md) |

This document covers **MCP client** configuration (external tools into Aquila).

## Configuration

### Desktop Settings

Open **Runtime Settings → MCP servers**. Paste a JSON array:

```json
[
  {
    "name": "mongodb",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "mongodb-mcp-server"],
    "env": {},
    "enabled": true
  },
  {
    "name": "remote-api",
    "transport": "sse",
    "url": "http://127.0.0.1:8081/sse",
    "enabled": false
  }
]
```

Click **Save MCP servers**, then **Reconnect MCP**.

### Instance override

Per-instance servers merge with app settings in [`Agent-Instances/{id}/profile.json`](../Agent-Instances/) under `mcp_servers`.

### Remote PWA

- `GET /api/mcp/servers` — list + health
- `PUT /api/mcp/servers` — save and reconnect
- `POST /api/mcp/test/{server_name}` — test one server

## Tool naming

MCP tools appear as:

```
mcp__{server}__{tool_name}
```

Example: `mcp__mongodb__find`

They are merged into the agent tool registry at startup and included in routed schemas when the active mode allows MCP.

## Mode policy

Default allowed modes (`AQUILA_MCP_ALLOWED_MODES`):

```
autonomous,task,research,code,writing
```

Set to `autonomous,task` to keep code/research loops lean.

## Security

- MCP servers run only from explicit user configuration (Settings or profile JSON).
- Stdio servers spawn subprocesses with the configured command/args/env.
- SSE servers connect only to configured URLs.
- Tool arguments pass through the same executor path as native tools.

## Implementation

| File | Role |
|------|------|
| [`agent/core/mcp_bridge.py`](../agent/core/mcp_bridge.py) | Bridge: connect, list_tools, call_tool |
| [`agent/storage/runtime_settings.py`](../agent/storage/runtime_settings.py) | `load_app_mcp_servers` / `save_app_mcp_servers` |
| [`agent/core/main.py`](../agent/core/main.py) | `Agent.refresh_mcp_tools()` |
| [`agent/core/loop_engine.py`](../agent/core/loop_engine.py) | MCP tools in routed schema |
| [`agent/gui/gui_pages/settings_page.py`](../agent/gui/gui_pages/settings_page.py) | MCP JSON editor |

## Dependencies

```
pip install mcp>=1.0.0
```

Listed in [`requirements.txt`](../requirements.txt).

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No MCP tools in Autonomous | Server `enabled: true`, mode in `AQUILA_MCP_ALLOWED_MODES`, reconnect in Settings |
| `mcp not installed` | Install `mcp` package in your venv |
| Stdio server fails | Command path, args, env vars; test manually in a shell |
| SSE server fails | URL reachable, CORS/network, server supports MCP SSE transport |

See also: [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md) for how MCP fits under 5.0 multi-worker parallelism.

**Host (Cursor):** [aquila-mcp-host.md](aquila-mcp-host.md)
