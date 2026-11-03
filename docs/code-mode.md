# Code mode (filesystem tools)

> **Roadmap:** [reliability-plan/](reliability-plan/README.md) — Phase 1 FS tools, Phase 2 context layer, Phase 3 LoopEngine frozen for code.

Code mode is a **chat-like coding loop** — no planner, no plan review, no agent sync step. `LoopEngine` refuses `mode=code`; entry is always `code_agent.run_tool_session`.

## How it works

1. User describes what to build or fix in the Code IDE.
2. Aquila runs a multi-turn session: each turn the model picks **one** filesystem tool.
3. Writes go **directly to disk** under `CODE_PROJECT_ROOT`.
4. Session ends when the model sets `final_report` (or turn limit).

## Project scope (canvas)

`active_code_state.json` holds **GUI project metadata** (name, root path) only. It is not a write buffer for the agent. Optional IDE “Sync buffer” flushes GUI-side edits; agent tools never require `cap.dev.sync_project`.

## Tools

| Tool | Purpose |
|------|---------|
| `read_file` | Read file with line numbers (`start_line`, `end_line`) |
| `write_file` | Create or overwrite file on disk |
| `search_replace` | Exact single-match edit |
| `list_dir` | Directory tree |
| `grep` | Search file contents |
| `find_files` | Glob filenames under project root |
| `run_command` | Allowlisted shell (pytest, python, git, etc.) |
| `semantic_search` | Chroma semantic search (env-gated, default off) |

## Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `AQUILA_CODE_MAX_TURNS` | `16` | Max LLM turns per session |
| `AQUILA_CODE_MAX_WRITE_CHARS` | `8000` | Max `write_file` content per call |
| `AQUILA_CODE_MODEL_GATE` | `1` | Enforce model tier checks for Code Mode |
| `AQUILA_CODE_ALLOW_DEGRADED_MODEL` | `0` | Allow degraded models in CLI/harness (GUI always blocks) |
| `AQUILA_CODE_SESSION_LOG` | `1` | Append session metrics to `Agent-Logs/code-sessions.jsonl` |
| `AQUILA_RUN_COMMAND` | `1` | Enable `run_command` tool |
| `AQUILA_CODE_SNAPSHOT_MAX_CHARS` | `8000` | Project tree + key files in system prompt |
| `AQUILA_CODE_AUTO_CONTEXT` | `0` | Auto-inject grep hit snippets on next turn |
| `AQUILA_CODE_AUTO_CONTEXT_MAX_CHARS` | `12000` | Cap on auto-context block size |
| `AQUILA_CODE_SEMANTIC_SEARCH` | `0` | Enable `semantic_search` tool (lazy Chroma index) |
| `AQUILA_TOOL_OUTPUT_CHAR_CAP` | `6000` | Max chars per tool output appended to loop |

## Context layer (Phase 2)

At session start, a shallow directory tree and key file list are injected into the `--- PROJECT ---` system prompt block. Optional features:

- **`find_files`** — always available; glob under project root (e.g. `**/test_*.py`)
- **`semantic_search`** — requires `AQUILA_CODE_SEMANTIC_SEARCH=1`; uses local embeddings via `agent/storage/embeddings.py` (hash fallback by default; ONNX MiniLM only if already cached — set `AQUILA_ALLOW_EMBEDDING_DOWNLOAD=1` to fetch)
- **`AQUILA_CODE_AUTO_CONTEXT=1`** — after `grep` with 1–3 unique file hits, prepends a `read_file` snippet on the next turn

Implementation: `agent/policies/code_context.py`

## Model requirements

Code Mode requires a **capable** local model (harness-verified). Recommended:

```env
OLLAMA_MODEL=aquila:latest
```

| Tier | Models | Behavior |
|------|--------|----------|
| Capable | `aquila`, `aquila:latest` | Full Code Mode |
| Degraded | `aquila-qwopus-standard`, `aquila_qwopus` | Blocked in GUI; CLI warns unless override |
| Unknown | other tags | Warn; session allowed |

Registry: [`agent/policies/model_tiers.py`](../agent/policies/model_tiers.py)

## Harness gate

Before shipping code-mode changes, run:

```bash
./scripts/harness_gate.sh
./scripts/harness_gate.sh --runs 3 --baseline
./scripts/harness_gate.sh --allow-degraded
```

Required scenarios: `code_smoke_file`, `code_habit_tracker`.

## Artifacts

- Project root: `Agent-Code/<project>/` (`active_code_state.json` = GUI scope metadata only)
- Session metrics: `Agent-Logs/code-sessions.jsonl`
- Harness reports: `Agent-Logs/capability-runs/`

**Note:** Agent edits are immediate on disk. Use git in your project if you need history. GUI buffer sync is optional and not part of the agent happy path.

## Implementation

- `agent/core/code_agent.py` — tool session loop
- `agent/tool_library/code_agent_tools.py` — FS tool implementations
- `agent/policies/code_tool_catalog.py` — tool registry + JSON schema
- `agent/core/code_session_metrics.py` — per-session metrics + JSONL
- `agent/core/harness_gate.py` — gate runner
- `agent/policies/code_context.py` — project snapshot + auto-context policy

## Tests

```bash
python -m pytest agent/tests/test_code_agent_tools.py agent/tests/test_code_agent_loop.py agent/tests/test_code_context.py agent/tests/test_semantic_search_tool.py agent/tests/test_code_tool_catalog.py agent/tests/test_code_chat.py agent/tests/test_model_tiers.py agent/tests/test_harness_gate.py -q
```
