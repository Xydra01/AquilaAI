# Aquila maintenance checklist

## After loop / tool refactors

1. `cd agent && pytest tests/ -v --tb=short` (Ollama running for live tests)
2. Confirm `AQUILA_LEGACY_ACT_REFLECT` unset (continuous loop default)
3. Smoke: code task writes `ARCHITECTURE.md` with `Step · Episode` log headers

## Post-refactor path audit

After the `agent/` subpackage move, grep docs for stale flat paths:

```bash
rg 'agent/gui/gui_pages/|agent/gui/gui_widgets/|agent/main\.py|agent/loop_engine|agent/mcp_bridge|agent/capability_harness|agent/runtime_settings|python agent/gui\.py' --glob '*.md'
```

Canonical locations:

| Area | Path |
|------|------|
| Brain / loop | `agent/core/main.py`, `agent/core/loop_engine.py` |
| MCP | `agent/core/mcp_bridge.py`, `agent/core/mcp_host.py` |
| GUI | `agent/gui/gui.py`, `agent/gui/gui_pages/` |
| Settings storage | `agent/storage/runtime_settings.py` |
| Research guards | `agent/research/url_visit_registry.py` |
| Harness | `agent/core/capability_harness.py` |

Launch GUI: `python agent/gui/gui.py` or `./start.sh`.

## Tool naming

- Canonical names live in `agent/policies/tool_catalog.py` (`TOOL_ALIASES`, `STEP_KIND_TOOLS`)
- Grep for stale strings: `REFLECT_SCHEMA`, `streamlit`, duplicate `search_files` docs

## Feature flags (env)

| Variable | Default | Effect |
|----------|---------|--------|
| `AQUILA_ENABLE_DATA_PROCESSING` | `0` | Show Data Processing workspace in GUI |
| `AQUILA_ENABLE_THINK` | `1` | Native thinking on supported models |
| `AQUILA_DYNAMIC_LOOP` | on | Milestone-driven loop ([loop-dynamic.md](loop-dynamic.md)) |

## Local-only artifacts (not in Git)

- `standalone_cnn_toolkit/` — CNN training toolkit
- `overnight_pipeline_manager.py` — local overnight training orchestrator
- `models/`, `*.pth` — trained weights ([vision-and-cnn.md](vision-and-cnn.md))
