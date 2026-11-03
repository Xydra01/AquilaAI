# Phase 2: Context Layer



**Status:** Complete  

**Estimate:** 1–2 weeks  

**Depends on:** [Phase 1](phase-1-enterprise-code-tools.md)  

**Blocks:** — (enhances Phase 4)



## Goal



Reduce turns spent finding files — inject useful context automatically without adding planner/FSM complexity.



## Problem



Code mode today forces the model to:

1. Call `list_dir` / recon manually

2. Read files in small chunks

3. Build mental map over many turns



Enterprise agents pre-index the repo and inject relevant snippets. Aquila has Chroma + `grep_repo` but they are not wired into the code tool loop.



## Deliverables



### 2.1 — Session startup context



- [x] New: `agent/policies/code_context.py`

  - `build_project_snapshot(root, max_tokens=2000)` — shallow tree + key files list

  - Called once at `run_tool_session` start

  - Injected into system prompt `--- PROJECT ---` block



### 2.2 — Grep tool (if not done in Phase 1)



- [x] Confirm `grep` in `CODE_AGENT_TOOLS` with ripgrep-speed search

- [x] Respect `.gitignore` / `is_ignored_code_path` (minimal root `.gitignore` dir skip)

- [x] Output: `path:line: content` format (max matches cap)



### 2.3 — Semantic search tool (optional, local)



- [x] New tool: `semantic_search`

  - Query Chroma collection over project files

  - Reuse `_index_codebase` from `coding_tools.py` + `get_aquila_embedding_function()`

- [x] Index on session start (async or lazy first call)

- [x] Behind env: `AQUILA_CODE_SEMANTIC_SEARCH=1` (default off until perf validated)



### 2.4 — Auto-context policy



- [x] Env: `AQUILA_CODE_AUTO_CONTEXT=1`

- [x] After `grep` with ≤3 hits: optionally prepend top file snippet to next turn's user message

- [x] Hard cap: 12k chars total tool output per turn (existing pattern)

- [x] Never auto-inject without cap — avoid context explosion



### 2.5 — `find_files` helper tool (optional)



- [x] `find_files(glob_pattern)` — fast glob under project root

- [x] Simpler than full semantic search for "find all test files"



### 2.6 — Tests



- [x] `agent/tests/test_code_context.py` — snapshot size, ignore rules

- [x] `agent/tests/test_semantic_search_tool.py` — mock Chroma

- [x] Harness: `code_local_read` scenario updated for tool loop



### 2.7 — Docs



- [x] Update [code-mode.md](../code-mode.md) — context env vars

- [x] Note embedding model requirements (local)



## Files to touch



| File | Change |

|------|--------|

| `agent/policies/code_context.py` | **New** |

| `agent/tool_library/code_agent_tools.py` | `semantic_search`, `find_files` |

| `agent/core/code_agent.py` | Inject snapshot; auto-context hook |

| `agent/tool_library/coding_tools.py` | Expose index helper for code projects |

| `docs/code-mode.md` | Env table |



## Exit criteria



- [x] Project snapshot appears in every code session system prompt

- [ ] `code_local_read` harness passes with ≤ baseline turns − 20% (manual harness run when Ollama available)

- [x] `grep` finds symbols across project without manual recon

- [x] Semantic search off by default; passes unit tests when enabled

- [x] No regression on Phase 0 gate scenarios — smoke **3/3** (`aquila:latest`, 2026-09-06)



## Env vars



| Variable | Default | Meaning |

|----------|---------|---------|

| `AQUILA_CODE_AUTO_CONTEXT` | `0` | Auto-inject grep hit snippets |

| `AQUILA_CODE_AUTO_CONTEXT_MAX_CHARS` | `12000` | Cap on auto-context block |

| `AQUILA_CODE_SEMANTIC_SEARCH` | `0` | Enable semantic_search tool |

| `AQUILA_CODE_SNAPSHOT_MAX_CHARS` | `8000` | Project tree in system prompt |



## Risks & open questions



| Item | Notes |

|------|-------|

| Index build time | Large repos may slow session start — lazy index |

| Embedding model size | Must stay local; document RAM requirements |

| Auto-context noise | May confuse weak models — keep off by default |

| LSP integration | **Deferred** — high effort; semantic search is 80% value |



## Out of scope



- Full LSP / type-aware navigation

- Cross-repo context (monorepo roots)

- Cloud embedding APIs



## Metrics to track



| Metric | How |

|--------|-----|

| Turns for `code_local_read` | Harness report |

| Avg turns per code session | `Agent-Logs/code-sessions.jsonl` |

| Index build wall time | Log on session start (`metrics.extra.index_wall_ms`) |

