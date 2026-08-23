# Aquila MCP Host (Cursor + Aquila in parallel)

Aquila can **host** an MCP server with six high-level meta-tools so Cursor (or any MCP client) delegates heavy local Ollama work without loading Aquila’s full native tool catalog.

This is the **inverse** of [mcp-integration.md](mcp-integration.md) (Aquila as MCP **client**).

## Why

| Cursor alone | Cursor + Aquila MCP host |
|--------------|---------------------------|
| Large tool/context surface for repo work | ~6 MCP tools in Cursor context |
| Cloud or frontier model for everything | Local Ollama for research/code/writing loops |
| Full conversation in Cursor | Compact `ModeResult` JSON + deliverable path back |

## Meta-tools

| Tool | Description |
|------|-------------|
| `aquila_health` | Ollama reachability, model, instance, generation lock |
| `aquila_list_instances` | Instance profiles |
| `aquila_run_mode` | Headless research / code / writing / task loop |
| `aquila_run_autonomous` | Full Autonomous Task run |
| `aquila_get_task_status` | Read step ledger JSON |
| `aquila_get_task_metrics` | Live tokens/s, slow detection, ETA from `Agent-Logs/*.jsonl` |
| `aquila_probe_throughput` | Quick Ollama streaming benchmark (TTFT + est. tokens/s) |
| `aquila_read_deliverable` | Bounded read of output `.md` |
| `aquila_list_scenarios` | Harness scenario catalog |
| `aquila_run_scenario` | Run predefined scenario (`engine`: stock/tq) |
| `aquila_evaluate_run` | Score run + write capability-runs report |
| `aquila_release_generation_lock` | Clear stale generation lock |

Recursive dev loop: [aquila-recursive-harness.md](aquila-recursive-harness.md).

## Cursor setup (stdio)

Add to `.cursor/mcp.json` (adjust paths):

```json
{
  "mcpServers": {
    "aquila": {
      "command": "F:/Users/myfri/agent-projects/ai-agent-env/Scripts/python.exe",
      "args": ["F:/Users/myfri/agent-projects/agent/core/mcp_host.py"],
      "env": {
        "AQUILA_DATA_ROOT": "F:/Users/myfri/agent-projects"
      }
    }
  }
}
```

On Windows, use the **full path** to `mcp_host.py` in `args` (Cursor may ignore `cwd` and look in your user folder).

Or use the helper script from repo root:

```bash
./scripts/aquila-mcp-serve.sh
```

## Remote Companion (SSE)

When the Remote Companion is running (`scripts/aquila-remote-serve.sh`), the same tools are available at:

- SSE base: `http://127.0.0.1:8800/api/mcp/host/sse`
- Messages: `http://127.0.0.1:8800/api/mcp/host/messages/`

Authentication: paired device token via `Authorization: Bearer <token>` or query `?token=`.

Pair a device first (`POST /api/pair`), then configure Cursor MCP SSE URL with token.

Standalone dev SSE (no Remote Companion):

```bash
cd agent
python mcp_host.py --sse --port 8765
```

## Throughput monitoring

While a task runs, poll **`aquila_get_task_metrics`** with the `task_name` / `delegation_id` from `aquila_run_mode`:

- `throughput.last_tokens_per_s` — estimated from each `llm_response` in the run JSONL
- `throughput.health` — `ok` / `degraded` / `slow` vs `AQUILA_EXPECTED_TOKENS_PER_S` (default **30**)
- `progress.eta_seconds` — rough estimate from ledger step index and elapsed wall time

Before a long run, call **`aquila_probe_throughput`** to confirm Ollama is warm (~30 t/s at 32k non-TQ is typical on your GPU).

| Variable | Default | Meaning |
|----------|---------|---------|
| `AQUILA_EXPECTED_TOKENS_PER_S` | 30 | Baseline for stock Ollama (`:11434`) |
| `AQUILA_TQ_EXPECTED_TOKENS_PER_S` | 30 | Baseline for TurboQuant (`:11435`); falls back to stock value |
| `AQUILA_SLOW_TPS_RATIO` | 0.5 | Below baseline × ratio → `slow` |

Probe TurboQuant explicitly:

```text
aquila_probe_throughput(instance_id="ai-researcher", engine="tq")
aquila_probe_throughput(engine="both")   # stock + TQ side by side
```

Each `llm_response` in `Agent-Logs/*.jsonl` records `ollama_engine`, `output_tokens_per_s`, and `throughput_health` for the engine in use (including TQ).

## Local files (not just web research)

`aquila_run_mode` accepts:

- **`file_paths`** — comma-separated or JSON list, e.g. `agent/core/generation_lock.py,agent/core/main.py`
- **`prefer_local`** — `true` to steer away from `web_search` (use `read_file` / `grep`)

Research mode is web-oriented; for **repo-only** summaries prefer **`mode="code"`** with `file_paths` and a read/summarize objective.

Example:

```text
aquila_run_mode(
  mode="code",
  instance_id="preon-agent-1",
  objective="Summarize generation_lock.py and how run_unified_task acquires the lock.",
  file_paths='["agent/core/generation_lock.py","agent/core/main.py"]',
  prefer_local=true
)
```

## Recommended workflow

1. Cursor plans and edits locally (small context).
2. Cursor calls `aquila_run_mode(...)` for local work; poll `aquila_get_task_metrics` if the run is long.
3. Cursor reads `deliverable_path` from the JSON response or calls `aquila_read_deliverable`.
4. Cursor integrates results into the repo.

## Generation lock

Only **one** Aquila generation runs at a time across:

- PySide6 GUI tasks/chat
- Remote Companion
- MCP host (Cursor)

Lock file: `Agent-Instances/generation.lock`. If busy, tools return:

```json
{"status": "busy", "message": "Another Aquila generation is running ..."}
```

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `AQUILA_DATA_ROOT` | repo root | Data paths |
| `AQUILA_MCP_DELIVERABLE_CAP` | 12000 | Max chars for `aquila_read_deliverable` |

## Implementation

| File | Role |
|------|------|
| [agent/core/mcp_host.py](../agent/core/mcp_host.py) | FastMCP tools + stdio/SSE CLI |
| [agent/core/generation_lock.py](../agent/core/generation_lock.py) | Cross-process lock |
| [agent/instance_runtime.py](../agent/instance_runtime.py) | Instance Ollama setup |
| [agent/remote/mcp_host_mount.py](../agent/remote/mcp_host_mount.py) | SSE + auth on Remote Companion |

See also: [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md) (Cursor parallel lane).
