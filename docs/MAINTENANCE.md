# Aquila maintenance checklist

## After loop / tool refactors

1. `cd agent && pytest tests/ -v --tb=short` (Ollama running for live tests)
2. Confirm `AQUILA_LEGACY_ACT_REFLECT` unset (continuous loop default)
3. Smoke: code task writes `ARCHITECTURE.md` with `Step · Episode` log headers

## Tool naming

- Canonical names live in `agent/tool_catalog.py` (`TOOL_ALIASES`, `STEP_KIND_TOOLS`)
- Grep for stale strings: `REFLECT_SCHEMA`, `streamlit`, duplicate `search_files` docs

## Legacy UI

- Streamlit: `agent/legacy/streamlit_app.py` only — not `agent/app.py`
