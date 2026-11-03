# Phase 1: Enterprise Code Tools

**Status:** Implemented (2026-09-02); habit tracker gate **0/3** — model tuning ongoing  
**Estimate:** 2–3 weeks  
**Depends on:** [Phase 0](phase-0-baseline-and-gates.md) (including **0.7 gate honesty**)  
**Blocks:** Phase 2, Phase 3, Phase 4

## Carries forward from live baseline (A–E)

Items discovered from the 2026-09-01 live gate run. **Do not duplicate Phase 0.7** — Phase 1 builds the permanent fix on the new tool loop.

| ID | Phase 0.7 (bridge on `code_chat`) | Phase 1 (permanent on `code_agent`) |
|----|-------------------------------------|-------------------------------------|
| **A** | Honest `evaluate_run` for code sessions | Same rules; completion = files on disk (no `sync_project`) |
| **B** | Contract tests on `code_session_metrics` | Extend contracts for `ToolSessionMetrics` + tool names in reports |
| **C** | `args` → `arguments` heal for caps | Tool JSON heal only if needed; prefer flat `tool` + `arguments` schema |
| **D** | `create_file` size cap + repeat guard | `write_file` max size; `search_replace` for edits; loop repeat guard |
| **E** | Re-baseline after 0.7 (smoke 3/3) | Re-baseline after 1.8 (smoke + habit 3/3) |

## Goal

Replace code-mode capabilities + Code Canvas buffer with **sharp filesystem + shell tools** and a **simple tool loop** — matching Cursor / Claude Code / Codex primitives.

## Problem

Current code path:

```
LLM → cap.dev.* → code_canvas_tools → JSON buffer → sync_project → disk
```

Friction: `create_file` vs `edit_apply`, line limits (`MAX_NEW_FILE_LINES=80`), sync step, capability ID confusion, `heal_calls` for nested IDs.

## Target tool surface

| Tool | Args | Behavior |
|------|------|----------|
| `read_file` | `path`, `start_line?`, `end_line?` | Read with line numbers |
| `write_file` | `path`, `content` | Create or overwrite on disk |
| `search_replace` | `path`, `old_string`, `new_string` | Exact match; error if 0 or >1 match |
| `list_dir` | `path`, `max_depth?` | Directory listing / shallow tree |
| `grep` | `pattern`, `path?`, `glob?` | Wrap `grep_repo` |
| `run_command` | `command`, `cwd?`, `timeout_s?` | Subprocess in project root |

All paths relative to active `CODE_PROJECT_ROOT`.

## Deliverables

### 1.1 — Tool implementation

- [x] New module: `agent/tool_library/code_agent_tools.py`
  - [x] `read_file` — reuse `read_file_lines` / coding helpers
  - [x] `write_file` — direct write under project root; create parent dirs
  - [x] `search_replace` — read → find unique match → write
  - [x] `list_dir` — reuse `get_directory_tree` or lightweight listing
  - [x] `grep` — delegate to `tool_library/grep_tools.grep_repo`
  - [x] `run_command` — `subprocess.run`, capture stdout/stderr, timeout
- [x] Path safety: `resolve_under_data_root` / project scope checks (no escape)
- [x] Remove or raise artificial line limits for this path
- [x] Consistent result format: `✅` / `❌` prefix + body (match existing tool style)

### 1.2 — Tool registry for code mode

- [x] `agent/policies/code_tool_catalog.py` — **New**
  - Tool names, descriptions for prompt
  - JSON schema builder for Ollama `format` (flat enum + arguments object)
- [x] Reuse patterns from `build_capability_action_json_schema` where possible

### 1.3 — Tool loop

- [x] New: `agent/core/code_agent.py`
  - Generic `run_tool_session(agent, user_request, tools, system_prompt, ...)`
  - One tool per turn (initially)
  - Parse → validate → execute → append `Tool Outputs:` to messages
  - Cancel check, thinking callback, ui_callback (port from `code_chat.py`)
- [x] `CODE_AGENT_TOOLS` frozenset of allowed tool names
- [x] **Observability (optional):** emit `tool_start` / `tool_end` JSONL via `RunLogger` so scorecard and session metrics agree
- [x] **Loop guards (D):** repeat same tool+path 3× → hard coach or stop; track in `ToolSessionMetrics`

### 1.3b — Tool argument heal (C, if needed)

- [x] Lightweight `_heal_tool_action()` for `capabilities[]` bridge + `path`/`file_path` aliases
- [ ] Full `heal_tool_call()` only if eval still shows >5% parse/heal rate after prompt tuning

### 1.3c — Write limits (D)

- [x] `write_file`: max content chars (env `AQUILA_CODE_MAX_WRITE_CHARS`, default 8000); clear error directing to `search_replace` for edits
- [x] No silent truncation — reject oversized writes

### 1.4 — Prompt

- [x] `get_code_agent_prompt()` in `agent/core/prompts.py`
  - Enterprise-style rules: read before edit, `search_replace` over full rewrite, run tests
  - No capability IDs, no plans, no sync step
- [x] Deprecate `get_code_chat_prompt()` → delegate to `get_code_agent_prompt()`

### 1.5 — Wire entry points

- [x] `main.py` `_run_unified_task_impl`: `mode == "code"` → `run_tool_session`
- [x] GUI `code_ide_page.py`: unchanged API (still calls `run_unified_task`)
- [x] MCP code paths (if any): update to tool loop

### 1.6 — Project root handling

- [x] On empty project: `write_file` or init helper creates project dir under `Agent-Code/`
- [ ] Optional: keep `project_setup` as a **tool** (`init_project`) not a capability
- [x] Document project root in system prompt each session

### 1.7 — Tests

- [x] `agent/tests/test_code_agent_tools.py` — each tool on temp directory
- [x] `agent/tests/test_code_agent_loop.py` — mock LLM, verify dispatch
- [x] Migrate `test_code_chat.py` → `test_code_agent.py`
- [x] **B:** contract tests — `evaluate_run` passes when tool session completes + files on disk
- [x] `write_file` oversize rejection test (D)
- [x] Update harness scenarios to expect tool names in reports (optional field)

### 1.8 — Transitional deprecation

- [x] `code_chat.py` — thin wrapper calling `code_agent` for one release, then delete
- [x] `cap.dev.*` — keep registered but not used by default code path
- [x] Update [code-mode.md](../code-mode.md) with new tool list

### 1.9 — Harness & evaluation alignment (A, E)

- [x] Update `code_smoke_file` / `code_habit_tracker` scenario context for **tool names** (not `cap.dev.*`)
- [x] `evaluate_run`: code mode passes on disk acceptance + session metrics (`completed` flag; no `sync_project`)
- [x] **E:** `./scripts/harness_gate.sh --runs 3 --baseline` — smoke **3/3**; habit **0/3** (2026-09-02)
- [ ] Update `CODE_CAPABLE_MODELS` only after habit passes (Phase 5 promotion gate)

## Files to touch

| File | Change |
|------|--------|
| `agent/tool_library/code_agent_tools.py` | **New** |
| `agent/policies/code_tool_catalog.py` | **New** |
| `agent/core/code_agent.py` | **New** |
| `agent/core/code_chat.py` | Deprecate → wrapper |
| `agent/core/main.py` | Wire tool loop |
| `agent/core/prompts.py` | `get_code_agent_prompt()` |
| `agent/tests/test_code_agent_*.py` | **New** |
| `docs/code-mode.md` | Rewrite for tools |

## Exit criteria

- [x] `code_smoke_file` harness passes via tool loop (**3/3**)
- [ ] `code_habit_tracker` harness passes via tool loop (gated model, 3/3) — **0/3** as of 2026-09-02
- [x] No `sync_project` required for code session completion
- [x] `write_file` + `search_replace` + `run_command` covered by unit tests
- [x] Phase 0 gate script runs; smoke green

## Success metrics

| Metric | Target |
|--------|--------|
| `code_smoke_file` turns | ≤ 4 |
| `code_habit_tracker` wall time | < 45s on gated model |
| Parse failures per session | < 5% |

## Risks & open questions

| Item | Notes |
|------|-------|
| `search_replace` uniqueness | Enterprise uses this; may need `replace_all` flag later |
| `run_command` security | Sandbox to project root; block `rm -rf /` patterns? |
| GUI undo without buffer | **Open:** git-based undo vs keep buffer as optional layer |
| Multi-tool per turn | Defer until model eval (Phase 5) shows >95% single-tool reliability |
| Windows shell | Ensure `run_command` works on win32 (user's OS) |

## Out of scope

- Semantic search (Phase 2)
- Deleting `LoopEngine` code branches (Phase 3)
- Fine-tuning (Phase 5)

## Reference: enterprise parity checklist

- [x] read_file with line numbers
- [x] write / search_replace
- [x] grep
- [x] list directory
- [x] run shell command
- [ ] apply_patch (unified diff) — add if `search_replace` insufficient
- [ ] git diff/status — Phase 6 or later
