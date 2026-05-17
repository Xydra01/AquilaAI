## Summary

This PR merges **Aquila OS 3.2** into `main`: a major stabilization release after 3.1's research-complete milestone. The primary interface moves from Streamlit to a **PySide6 desktop app**, adds **Writing Mode** end-to-end, hardens the **JSON tool-calling loop** for Ollama constrained decoding, introduces **file attachments** across modes, and ships a **pytest suite** (~30 modules, 98+ tests) plus full **README** and **ARCHITECTURE** documentation.

3.2 is intended as the production-ready baseline before **3.3** (planner budgets, loop engine refactor, reflect/act turns).

---

## What changed (high level)

### UI and UX
- **New primary UI:** `agent/gui.py` (PySide6) — dark theme, streaming chat, autonomous/research/writing modes, cancel, resume ledgers, attachment picker
- **Task State Tracker:** `gui_state.py` resolves ledgers for autonomous (`Agent-Tasks/`), research (`Agent-Plans/`), and writing (`Agent-Drafts/`) with live HTML step rendering
- **Chat fixes:** single completion bubble (`chat_finished` vs `task_finished`); **Clear Chat View** clears display only while preserving model history
- **Legacy:** `agent/app.py` (Streamlit) remains but is **not maintained** for 3.2

### Agent brain (`agent/main.py`)
- **Dynamic strict JSON schema** via `build_strict_schema()` — per-tool `anyOf` branches from signatures; `additionalProperties: false`
- **Non-streaming tool turns** (`stream=False`) — fixes schema drift (e.g. `tool_name` vs `name`)
- **`validate_tool_calls()`** — rejects malformed tool objects without silent repair
- **Loop guards:** max 6 tools/turn, parse/schema retry (max 2), duplicate-tool warning, forced advance on stall, iteration limits per step
- **Deliverables:** `save_task_deliverable()` → `Agent-Research/` or `Agent-Creations/`; `complete_ledger_state()` on `finish_task`
- **Attachments:** `format_attachment_context()` injected in planner + first loop turn
- **Lazy `global_agent`** proxy for faster test collection
- **`_index_codebase` excluded** from executable tool schema

### New / expanded capabilities
- **Writing Mode** (`tool_library/writing_tools.py`): `init_document`, `write_section`, `read_outline`, `compile_final_document`
- **File parser** (`file_parser.py`): PDF, DOCX, CSV, HTML, images, 5MB cap, many text/code types
- **Prompts split** (`prompts.py`): chat, autonomous, research, writing with shared base context
- **Memory singleton** (`memory_singleton.py`): shared scratchpad between `main` and `agent_tools`
- **Sleep cycle:** consolidates `Agent-Tasks/` **and** `Agent-Plans/`

### Engineering
- **`requirements.txt`** at repo root
- **`agent/pytest.ini`**, `conftest.py`, fixtures, 30+ test modules
- **`README.md`** — setup, modes, tools, testing, troubleshooting
- **`ARCHITECTURE.md`** — 596-line technical reference
- **`.gitignore`** — allow `README.md` / `ARCHITECTURE.md` while keeping agent output `.md` ignored

---

## Commits in this PR (7 + docs)

| Commit | Description |
|--------|-------------|
| `430559a` | Initial transition from Streamlit to Qt |
| `dd97de6` | Split prompts; chat context; Qt dark mode + ledger tab |
| `7037f7b` | Writing tools; file/image attachments in UI |
| `63f4ebf` | Start pytest suite |
| `8531290` | Tests for features and edge cases |
| `b67627f` | CSV/XLSX/HTML parser; chat history; security checks |
| `202aff1` | README + ARCHITECTURE documentation |

---

## Stats

47 files changed, ~3700 insertions, ~375 deletions (vs Aquila-3.1)

Key files: `agent/main.py`, `agent/gui.py`, `agent/prompts.py`, `agent/file_parser.py`, `agent/gui_state.py`, `agent/tool_library/writing_tools.py`, `agent/tests/*`, `requirements.txt`

---

## Breaking / behavioral notes

1. **Run from repo root** — `Agent-*` folders and `AGENT_ROOT_DIR` use `os.getcwd()`.
2. **Ollama model name** is hardcoded `aquila` — build with repo `Modelfile`.
3. **SearXNG required** for research `web_search` (`docker compose up -d`).
4. **Streamlit** (`app.py`) is not the supported 3.2 entry point; use `start.sh` / `python agent/gui.py`.

---

## Test plan

- [ ] `cd agent && pytest tests/ -q` (exclude live tests if Ollama unavailable)
- [ ] `pytest tests/ -m live` with Ollama running and `aquila` model loaded
- [ ] `./start.sh` or `python agent/gui.py` from repo root
- [ ] **Chat:** send message + optional image attachment; verify single response bubble
- [ ] **Autonomous:** create and run a small Python script; verify `Agent-Tasks/{name}.json` advances and completes
- [ ] **Research:** run a cost/comparison query; verify `Agent-Research/{task}.md` deliverable
- [ ] **Writing:** 3-section essay; verify `Agent-Drafts/` output and `compile_final_document`
- [ ] **Resume:** restart GUI mid-ledger; tracker shows correct step
- [ ] **Sleep cycle:** complete a task, run consolidation; check episodic memory update
- [ ] **SearXNG:** `curl 'http://localhost:8080/search?q=test&format=json'` returns results

---

## Known issues (accepted for 3.2; 3.3 planned)

- Planner `max_iterations` often too low → OS forced advance before objective fully done on complex steps
- Duplicate tool calls / re-reads under budget pressure (grep-style tasks)
- `route_tools()` implemented but not wired into loop
- Parse failures on very large `save_research_note` payloads can burn iterations
- Cwd-sensitive paths if not launched from repo root

---

## Documentation

- [README.md](../README.md) — user-facing setup and usage
- [ARCHITECTURE.md](../ARCHITECTURE.md) — full system design reference

---

## Reviewer focus areas

1. `build_strict_schema` + non-streaming tool loop — correctness vs Ollama version
2. `gui.py` thread signals and cancel/resume paths
3. `is_safe_path` / tool security boundaries
4. Test mocks vs real `Agent()` init (Chroma indexing cost)
