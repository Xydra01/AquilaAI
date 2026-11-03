# Aquila-cpp Recon Map

Living reference for the C++20 rebuild of Aquila. Update it whenever a fact changes; every claim below is tagged with how it was established:

- **[measured]**: produced by a command in "How to re-verify" below.
- **[code file:line]**: read directly from source.
- **[doc]**: taken from repo docs and not yet re-verified against code (docs are partly stale; see Hazards).
- **[proposal]**: my recommendation, not a decision. Needs sign-off.

Companion file: `PY_INVENTORY.md` (generated, per-file classes/functions/LOC/git state; never hand-edit).

## How to re-verify

The Python reference is a separate checkout of branch `Aquila-3.5` at `F:\Users\myfri\agent-projects` (pinned SHA in section 1). The inventory script finds it via `--py-ref`, `AQUILA_PY_REF`, or the sibling default `../agent-projects`.

From the Aquila-cpp root (`F:\Users\myfri\Aquila-cpp`):

```bash
python docs/recon/tools/py_inventory.py           # regenerate PY_INVENTORY.md
python docs/recon/tools/py_inventory.py --check   # every non-test .py must appear in this map
```

From the Python checkout (`F:\Users\myfri\agent-projects`):

```bash
git rev-parse HEAD                                 # must equal the pinned reference SHA
rg -o --no-filename 'AQUILA_[A-Z0-9_]+' agent --glob '*.py' --glob '!agent/tests/**' | sort -u | wc -l   # 152
```

Registry counts (needs `ai-agent-env`, see Environment). Note that importing `agent` opens a connection to Ollama:

```bash
AQUILA_DATA_ROOT=$(mktemp -d) AQUILA_SKIP_MIGRATE=1 ai-agent-env/Scripts/python.exe -c "import sys;sys.path.insert(0,'agent');from agent.tool_library import ALL_TOOLS;from agent.core.tools import SURVIVAL_TOOLS;from agent.capabilities.registry import CAPABILITY_REGISTRY as C;from agent.functions.recipes import RECIPE_REGISTRY as R;print(len(ALL_TOOLS),len(SURVIVAL_TOOLS),len(C),len(R))"
# expected at recon time: 74 10 44 15
```

---

## 1. Source of truth and environment

| Item | Value | Tag |
|---|---|---|
| Repo | `git@github.com:Xydra01/AquilaAI.git`, root = workspace root | [measured] |
| **Python reference (pinned)** | `Aquila-3.5` @ **`759212af3ae379f0c514e105dc97dd557cdaa0c0`**, pushed; local == `origin/Aquila-3.5` | [measured 2026-11-02] |
| How it got pinned | Recon started at `0e51872` with 143 dirty entries and 2 unpushed commits. The 156 files were committed as `759212a` (gitleaks: no leaks) and pushed `d982058..759212a`. Only the `tools/llama-cpp-turboquant` gitlink stays dirty (see the row below) | [measured] |
| C++ branch | `Aquila-cpp`, **orphan** (no shared history with Python), checked out as a git worktree at `F:\Users\myfri\Aquila-cpp` | [measured] |
| Remote branches | `main`, `Aquila-3.0`…`Aquila-3.5` | [measured] |
| Python env that works | `ai-agent-env/` (Python 3.12.11). Root `.venv/` (3.14.3) is **missing `mcp`** and cannot import `agent` | [measured] |
| Python test config | `agent/pytest.ini`, markers `live`, `heretic`, `qwopus`, `gui`. Run from `agent/` | [code] |
| C++ toolchain present | MSVC BuildTools 2022 14.44 (`F:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`), clang 22.1.5 (llvm-mingw UCRT), CMake 4.3.2, Ninja, CUDA 13.2 | [measured] |
| GPU | RTX 4070, 12282 MiB | [measured] |
| Existing llama.cpp | `tools/llama-cpp-turboquant` (fork `TheTom/llama-cpp-turboquant` @ `a62320c2c`, tracked as a gitlink with no `.gitmodules`), built with **MSVC cl.exe + nvcc, `GGML_CUDA=ON`** in `build-ninja/` | [measured: CMakeCache] |
| Local llama.cpp patches | The fork checkout has **uncommitted edits** in `common/arg.cpp`, `src/llama-model-loader.cpp`, `src/llama-model.cpp`, `src/models/qwen35.cpp`. Contents not reviewed. If they fix Qwen 3.5 loading, upstream may need the same fix (see D4) | [measured] |
| WSL | only `docker-desktop` distro (no Ubuntu) | [measured] |

**Implication:** "parity with Python" means parity with `759212a`. If the Python branch moves on, either re-pin here (and rerun the inventory) or check out `759212a` for parity work.

---

## 2. Design brief (Aquila_cpp.pdf), distilled into requirements

Line refs are to `pdftotext -layout` output of the attachment.

| ID | Requirement | PDF ref |
|---|---|---|
| R1 | Strict C++20: no raw owning pointers; `unique_ptr`/`shared_ptr`/RAII/`std::jthread` | L28-33 |
| R2 | 1-3 OS threads max (orchestrator, GPU worker, tool worker). **No async runtime, no coroutines**, mutex+condvar queue | L35-63, L119-121 |
| R2b | Later in the doc: prefer **fully single-threaded deterministic state machine** for the loop | L127-135, L347-353 |
| R3 | Header-only / FetchContent deps: nlohmann/json, cpp-httplib, spdlog+fmt, inja | L95-111, L536-539 |
| R4 | ASan+UBSan in debug from day one; TSan for queue tests | L112-117 |
| R5 | Port module-by-module with Python as the reference spec: data structures, then tool sandbox, then orchestration loop | L123-126 |
| R6 | Context condenser: pinned system prefix, anchored self-notes block, rolling tail of last K tools; wipe when over threshold | L138-162, L170-315 |
| R7 | Self-note is a **strict schema** (hypothesis, verified_facts, failed_approaches, next_action), enforced by grammar/structured output | L320-333 |
| R8 | Pre-truncate big tool outputs (head+tail), spill full output to a side buffer with a reference | L335-344 |
| R9 | ~10-15 atomic C++ primitives; **JSON recipes** chain them with `{{templating}}`, conditions, `on_failure`, `output_template`; recipe runner is itself a tool (`IToolPrimitive`), recursive | L359-539 |
| R10 | Escape hatches: plugin scripts in `tools/plugins/` with `manifest.json` (JSON over stdin/stdout); agent-authored recipes via `register_new_recipe` | L482-510 |
| R11 | Coarse-grained stateful modules (`IAgentModule`: `get_actions`, `execute_action`, `export/restore_state_snapshot`), e.g. Workspace / Execution / Knowledge / Orchestrator | L544-713 |
| R12 | Recipes load modules, scope exposed actions, `pre_llm_hooks`, `post_llm_validation_hook` exit gate | L715-793 |
| R13 | Module registry: compile-time first (Option A); DLL plugins (Option B) optional | L795-834 |
| R14 | `IInferenceBackend`: KV append, checkpoint, rollback, grammar-constrained generate, n-gram speculation, `ComputeProfile` | L1002-1077 |
| R15 | `RuntimeTierConfig`: one code path, tier-scaled knobs (condense threshold 2048/6144, rolling tools 2/4, tool output chars, thought tokens, gpu layers) | L1159-1210 |
| R16 | CPU-first discipline: physical-core thread pinning, repacked quants, BLAS for prefill | L895-928 |
| R17 | Model decision: **Qwen 3.5 family**, 4B CPU base + 9B GPU boost, optional 0.8B draft model | L1279-1324 |

**Corrections to the PDF, checked against local source:**

- `llama_kv_cache_seq_rm` (PDF L954) **does not exist** in the local llama.cpp. The current API is `llama_memory_seq_rm` / `llama_memory_seq_pos_max` (`tools/llama-cpp-turboquant/include/llama.h:714,766`). [measured]
- llama.cpp ships `json_schema_to_grammar(nlohmann::ordered_json)` (`common/json-schema-to-grammar.h:9`), so Aquila's existing strict JSON schemas can become GBNF directly (R7, R14). [measured]
- R4 on this machine: TSan is not available for Windows targets (MSVC or clang). TSan runs need Linux (Docker or a WSL distro). MSVC has ASan but no UBSan. [proposal: verify when setting up CMake presets]
- R2 vs R2b tension: the PDF argues for both 3 threads and zero threads. The Python app today runs the agent on a Qt worker thread with a cross-process generation lock (`agent/core/generation_lock.py`). [proposal: single-threaded loop core, plus at most 1 inference thread and 1 UI/IO thread at the edges]

---

## 3. Python codebase at a glance

[measured at `759212a`, see PY_INVENTORY.md] 466 `.py` files, 78,483 LOC. Non-test 255 files / ~59.8k LOC; tests 211 files / 18,678 LOC.

| Package | Files | LOC | Role | C++ disposition [proposal] |
|---|---:|---:|---|---|
| `agent/core` | 36 | 22168 | Brain: Ollama client, Agent, loop engine, planner, prompts, tools firewall, MCP, harness | Split; rewrite loop; see section 4 |
| `agent/gui` | 29 | 9052 | PySide6 desktop app, 9 workspaces | Decision D3 |
| `agent/tool_library` | 20 | 4191 | 74 tools merged into `ALL_TOOLS` | Collapse into ~10-15 primitives + modules (R9/R11) |
| `agent/storage` | 15 | 3984 | SQLite facts, Chroma vectors, instances, personas, learn, settings | Port (SQLite C API + vector index) |
| `agent/policies` | 15 | 3719 | Context budget/tiers, tool catalogs, step policies, think policy | Becomes `RuntimeTierConfig` + `ContextCondenser` + recipe scoping |
| `agent/capabilities` | 57 | 3266 | 44 versioned capabilities (Pydantic in → `CapabilityResult`) | Becomes `IAgentModule` actions |
| `agent/remote` | 13 | 2963 | FastAPI + WS server (52 routes) for PWA `webapp/` | Defer; keep HTTP/WS contract |
| `agent/parser` | 8 | 2656 | Strict schema builder, JSON parse/heal, Ollama diagnostics | Replace with nlohmann/json + schema → GBNF |
| `agent/research` | 10 | 1731 | Web enrichment, URL registry, content quality, light research | Port into KnowledgeModule |
| `agent/coding` | 7 | 1250 | File parser (PDF/DOCX/images), language registry, light coding | Port; PDF via MuPDF C |
| `agent/aquila_runtime` | 12 | 1170 | Hardware detection, Ollama/Docker/SearXNG bootstrap, paths | Port `hardware_profile` → `ComputeProfile` |
| `agent/functions` | 9 | 870 | Recipes (intent → capability list), writing brief/scope | Replace with JSON recipes (R9/R12) |
| `agent/vision` | 6 | 779 | torch CNN classifier (experimental) | Out of scope for core |
| `agent/tasks` | 1 | 243 | Headless data processor | Defer |
| `agent` (`agent/__init__.py`) | 1 | 120 | Legacy import aliases (`import main`, ...) | Drop |
| `scripts` | 3 py + 40 sh/ps1 | 994 (py) | Health check, Ollama install/serve, harness gate, packaging preflight | Keep as tooling; C++ build adds its own |
| `tests` (root) | 6 | 570 | Vision calibration scripts | Out of scope |
| `new_project` | 7 | 79 | Sample "galaga" project (agent output fixture) | Ignore / possible harness fixture |

### 3.1 Tool, capability, and recipe surfaces [measured]

- **Legacy tools:** `SURVIVAL_TOOLS` (10) + `ALL_TOOLS` (74) = 84, no overlap. (`ARCHITECTURE.md` §8 says 33, which is stale.)
- **Code-mode tool surface** (`agent/policies/code_tool_catalog.py`): `find_files, grep, list_dir, read_file, run_command, search_replace, write_file` (7). This is the PDF's "atomic primitives" in practice and the natural first port target.
- **Capabilities** (44): dev 12, research 10, writing 6, learn 5, plan 5, persona 4, web 2. Shape: `CapabilitySpec{id, version, input_model, handler, tier, modes}` (`agent/capabilities/registry.py:13-21`). Handler signature: `(CapabilityContext, BaseModel) -> CapabilityResult` (`agent/capabilities/base.py:100`).
- **Recipes** (15): `agent/functions/recipes.py`, just `recipe_id → tuple[capability_id]`. No data piping, conditions, or hooks. The PDF's recipe engine (R9/R12) is a strict superset.

### 3.2 Layer model (as documented, and as it really is)

Documented (`docs/capability-modules-vision.md` L7-12) [doc]:
`Tools → Tool modules → Capabilities → Function modules / recipes → Modes`

In reality the package graph is **cyclic** [measured, `rg` of imports]. Representative back-edges:

| Edge | Example |
|---|---|
| core → gui | `agent/core/mcp_host.py:111` `from agent.gui import resolve_ledger_path` |
| core → remote | `agent/core/mcp_host.py:233` `from remote.session import derive_task_name` |
| storage → core | `agent/storage/memory.py:131` `from agent.core import human_print` (6 sites) |
| parser → core | `agent/parser/structured_schema.py:927` `get_executable_tools` |
| capabilities → core | `agent/capabilities/dev/raw_tool.py:16-17` `get_executable_tools`, `ToolExecutor` |
| tool_library → core | `agent/tool_library/agent_tools.py:87-198` `resolve_task_id`, `save_task_deliverable` |
| aquila_runtime → core, remote | `agent/aquila_runtime/setup_health.py:4,6` |

Cycles are broken at runtime with function-local imports. `agent/core/__init__.py` (211 lines) is a facade that re-exports ~150 names that every layer reaches into.

---

## 4. `agent/core` in detail (biggest risk area)

[measured via AST] Monoliths:

| Symbol | Location | Size | Notes |
|---|---|---:|---|
| `LoopEngine` | `agent/core/loop_engine.py:64-5635` | 5572 lines, 73 methods | `_run_continuous_body` alone is **2604 lines** (L263) |
| `LoopEngine._execute_capability_batch` | `loop_engine.py:5256` | 380 | capability checkpoint → RunState |
| `LoopEngine._build_step_entry_messages` | `loop_engine.py:3577` | 338 | prompt assembly |
| `Agent` | `agent/core/main.py:2085-4203` | 2119 lines, 23 methods | `generate_plan` 762 (L2848), `_run_unified_task_impl` 475 (L3729) |
| `OllamaClient` | `main.py:273-1430` | 1158 lines | `chat` 554 (L877): streaming, think filter, kill switch, warmup, eject |
| `parse_agent_response` | `main.py:1539` | 221 | parse + heal |
| `ToolExecutor` | `main.py:1875-1931` | 57 | arg filtering by `inspect.signature` |
| `code_agent.run_tool_session` | `agent/core/code_agent.py:184` | 228 | **The "one dumb loop"**: model → parse → heal → one tool → append, 16-turn cap (untracked file) |

Core files, by role:

| Role | Files |
|---|---|
| Inference client | `agent/core/main.py` (`OllamaClient`, `_ThinkStreamFilter`), `agent/core/stdio_safe.py`, `agent/core/generation_lock.py` |
| Agent / modes | `agent/core/main.py` (`Agent.run_chat`, `run_*_chat`, `run_unified_task`, `initiate_sleep_cycle`), `agent/core/mode_runner.py`, `agent/core/delegation_tools.py`, `agent/core/chat_context.py`, `agent/core/walkthrough.py` |
| Legacy plan+act loop | `agent/core/loop_engine.py`, `agent/core/loop_coach.py`, `agent/core/loop_objectives.py`, `agent/core/loop_settings.py`, `agent/core/episode_tracker.py`, `agent/core/fast_path.py`, `agent/core/explore_agent.py` |
| Planner | `agent/core/plan_validator.py` (1548), `agent/core/plan_descriptions.py`, `agent/core/implementation_plan.py`, `agent/core/task_artifacts.py` |
| Code mode (new) | `agent/core/code_agent.py`, `agent/core/code_run_diagnostics.py`, `agent/core/code_scaffolds.py`, `agent/core/code_session_metrics.py` |
| Run state (scratchpad analogue) | `agent/core/run_state.py` (`TaskRunContext`, digest, checklist, ground truth), `agent/core/run_state_providers.py` (per-mode ground truth) |
| Prompts | `agent/core/prompts.py` |
| Tools + firewall | `agent/core/tools.py` (`SURVIVAL_TOOLS`, `is_safe_path`, `resolve_tool_path`), `agent/core/tool_result.py`, `agent/core/task_context.py` |
| MCP | `agent/core/mcp_bridge.py` (client stdio+SSE), `agent/core/mcp_host.py` (FastMCP host, 14 tools), `agent/core/mcp_attachments.py` |
| Harness / QA | `agent/core/capability_harness.py` (1056), `agent/core/capability_scorecard.py`, `agent/core/harness_gate.py` |
| Logging | `agent/core/run_logger.py` (console + JSONL) |
| Facade | `agent/core/__init__.py` |

**Current direction in the repo** (`docs/reliability-plan/README.md`) [doc]: "One dumb loop, sharp tools, batched capabilities." Phases 0-3 are marked done, and Phase 4 (unified ~300-line `agent_loop.py`) is not started. Code mode already bypasses `LoopEngine` (`loop_engine.py:187-191` raises for `mode=code`). **This lines up with the PDF**, so the C++ loop should be built from `code_agent.run_tool_session` semantics plus capability batches, *not* from `LoopEngine`.

---

## 5. Concept crosswalk: PDF design vs. existing Python

| PDF concept | Closest Python today | Gap / note |
|---|---|---|
| `ContextCondenser` (R6) | `agent/policies/context_manager.py` (`build_loop_messages`, `on_step_advance`, `compress_step_transcript`), `agent/policies/context_budget.py` | Python wipes `conversation_history` on step advance ([doc] ARCHITECTURE §5.5) and summarizes with an LLM call. No rolling-K tool tail as a first-class structure |
| `AgentScratchpad` / self-notes (R7) | `agent/core/run_state.py` `TaskRunContext` (goal, goal_summary, run_digest, checklist, milestones, ground_truth); SQLite `scratchpad` table via `save_research_note` | Not schema-enforced. Digest is free text |
| Pre-truncate tool output (R8) | `agent/policies/code_context.py` `truncate_text`/`tool_output_max_chars`; `format_capability_result_for_llm` 12k cap (`agent/capabilities/base.py:66-97`) | Head-only truncation. No spill buffer + reference |
| Atomic primitives (R9) | 7 code tools; 84 legacy tools | Consolidate |
| JSON recipes (R9/R12) | `agent/functions/recipes.py` (ordered cap IDs) | Need engine: templating, conditions, hooks, validation gate |
| `IAgentModule` (R11) | `CapabilitySpec` + handlers; `run_state_providers.py` ground-truth providers (= `export_state_snapshot`) | Capabilities are stateless functions. State lives in JSON files (`Agent-Code/active_code_state.json`, `Agent-Drafts/active_draft_state.json`) |
| Post-LLM validation gate (R12) | TDD soft gates in `loop_engine.py` ([doc] ARCH §17); `agent/core/harness_gate.py` | Make first-class |
| `IInferenceBackend` (R14) | `OllamaClient` (HTTP to Ollama `/api/chat`, `format`=JSON schema) | Ollama gives no KV control. Direct llama.cpp is needed for R6/R14 KV pinning |
| GBNF / structured output (R7/R14) | `agent/parser/structured_schema.py` (980) builds Ollama JSON schemas; `heal_calls.py` and `_heal_tool_action` patch arg aliases | Grammar at the sampler should remove most healing code |
| `RuntimeTierConfig` / `ComputeProfile` (R15) | `ContextProfile` tiers compact/standard/extended/max keyed on `num_ctx` (`agent/policies/context_budget.py:9-71`); `HardwareProfile` presets (`agent/aquila_runtime/hardware_profile.py:17-28`); `agent/policies/model_tiers.py`, `agent/policies/thinking_tiers.py` | Python keys on context size, PDF keys on hardware. Merge both |
| Plugins via stdin/stdout (R10) | MCP bridge (`agent/core/mcp_bridge.py`) is already a stdio JSON-RPC tool plugin mechanism | MCP may *be* R10. Decision D5 |
| Harness as proof | `agent/core/capability_harness.py` scenarios + `scripts/harness_gate.sh` | Reuse scenarios as cross-language parity tests |

---

## 6. Remaining packages (file-level)

### `agent/policies/` (all files)
Context, tool scoping, step policy. Key: `context_budget.py` (tiers), `context_manager.py` (condensing), `tool_catalog.py` (501, per-step allowlists), `step_policies.py` (1123, per-mode capability policies), `code_tool_catalog.py` + `code_context.py` (code mode), `model_tiers.py`, `thinking_tiers.py`, `think_policy.py`, `recon_policy.py`, `schema_policy.py`, `timeout_policy.py`, `tool_policy.py`, `doc_write_policy.py`.

### `agent/parser/` (all files)
`structured_schema.py` (schema builders for agent_action / capability_action / plan), `structured_parse.py` (parse+validate), `stream_output_guard.py` (degenerate repetition), `model_output_profile.py`, `ollama_messages.py`, `ollama_diagnostics.py` (CLI), `task_metrics.py`.

### `agent/capabilities/` (all files), with sub-packages `agent/capabilities/dev/` (all files), `agent/capabilities/learn/` (all files), `agent/capabilities/persona/` (all files), `agent/capabilities/planning/` (all files), `agent/capabilities/research/` (all files), `agent/capabilities/web/` (all files), `agent/capabilities/writing/` (all files)
Core files: `base.py`, `registry.py`, `adapters.py` (step_kind → default/allowed caps), `heal_calls.py`, `schema_hints.py`. Each sub-package registers handlers of ~30-110 lines that orchestrate tool_library calls.

### `agent/tool_library/` (all files)
`web_tools.py` (SearXNG + cloudscraper/BS4/markdownify), `coding_tools.py` (Chroma code index), `code_canvas_tools.py` (967, in-memory project buffer, patches), `code_agent_tools.py` (the 7 code tools), `agent_tools.py`, `os_tools.py`, `shell_tools.py`, `run_tools.py`, `grep_tools.py`, `git_tools.py`, `writing_tools.py`, `persona_tools.py`, `learn_tools.py`, `email_tools.py`, `calendar_tools.py`, `browser_tools.py`, `desktop_tools.py`, `data_tools.py`, `multimodal_tools.py`.

### `agent/storage/` (all files)
`memory.py` (DualMemorySystem: SQLite `facts`/`scratchpad` + Chroma `episodic_experiences`/`agent_tools`), `embeddings.py` (MiniLM ONNX → fallback hashing embedder), `memory_singleton.py`, `workspace_paths.py` (all `Agent-*` roots, `AQUILA_DATA_ROOT`), `instance_registry.py`, `instance_runtime.py`, `persona_registry.py`, `learn_registry.py`, `learn_index.py`, `chat_threads.py`, `config_catalog.py` (600, settings catalog), `runtime_settings.py`, `env_parser.py`, `preferences.py`.

### `agent/research/` (all files)
`web_enrichment.py`, `web_content_quality.py`, `url_visit_registry.py`, `web_search_query.py`, `search_config.py`, `light_research.py`, `light_research_plan.py`, `research_deliverable.py`, `research_journal.py`.

### `agent/coding/` (all files)
`file_parser.py` (attachments: images/PDF/DOCX/text), `pdf_text.py`, `language_registry.py` (lint/test dispatch), `light_coding.py`, `path_visit_registry.py`, `writing_canvas.py`.

### `agent/functions/` (all files)
`recipes.py`, `research.py`, `writing.py`, `writing_brief.py`, `writing_scope.py`, `learn.py`, `persona.py`, `code.py`.

### `agent/aquila_runtime/` (all files)
`hardware_profile.py`, `model_setup.py`, `ollama_bundle.py`, `docker_desktop.py`, `search_bundle.py`, `virtualization.py`, `paths.py`, `cpu_timeouts.py`, `setup_gate.py`, `setup_health.py`, `subprocess_win.py`.

### `agent/gui/` (all files), `agent/gui/gui_pages/` (all files), `agent/gui/gui_widgets/` (all files)
`gui.py` (1444, main window + `AgentWorker`/`ChatSubcallWorker`/`SleepWorker` threads), pages per mode (chat, task, research, writing, code IDE, character, learn 1097, settings 857, setup wizard, home, data), theme/formatting/richtext/state.

### `agent/remote/` (all files)
`server.py` (941, 52 FastAPI routes incl. `WS /api/chat`, `WS /api/task`), `session.py`, `tasks.py`, `auth.py`, `config.py`, `uploads.py`, `personas.py`, `learn.py`, `schemas.py`, `server_control.py`, `mcp_host_mount.py`, `host_cli.py`. Client: `webapp/` (vanilla JS PWA).

### Out of core scope
`agent/vision/` (all files) (torch CNN), `agent/tasks/` (all files), `tests/` (all files) (vision calibration), `new_project/galaga/galaga/` (all files), `new_project/galaga/tests/` (all files), `scripts/` (all files) (Python helpers: `benchmark_context.py`, `check-shell-unicode.py`, `packaged-preflight.py`), `agent/__init__.py` (legacy aliases).

---

## 7. Hazards (things that will bite the port)

| # | Hazard | Evidence |
|---|---|---|
| H1 | ~~Reference spec is uncommitted (143 entries) and 2 commits unpushed~~ **Resolved 2026-11-02:** pinned at `759212a`, pushed | [measured] git rev-parse / ls-remote |
| H2 | Cyclic package graph, held together by lazy imports and a 150-name facade | section 3.2 |
| H3 | Two import roots: `agent.x.y` and bare `tool_library...`, `main`, `remote.session` (needs `agent/` on `sys.path`) | `agent/remote/server.py:258` `import main as brain`; `agent/core/loop_engine.py:3818` |
| H4 | Import-time side effects: importing `agent` connects to Ollama | [measured] "Connected to Ollama at http://127.0.0.1:11434 (model: aquila:latest, num_ctx=96000)" |
| H5 | Dead code path: `AQUILA_LEGACY_ACT_REFLECT` imports a module that does not exist | `agent/core/loop_engine.py:193` `from loop_engine_legacy_snapshot import ...`; no such file in repo |
| H6 | 152 distinct `AQUILA_*` env vars, so behavior is heavily flag-dependent | [measured] |
| H7 | Monolithic methods (2604-line loop body, 762-line planner, 554-line chat). Port *behavior*, not structure | section 4 |
| H8 | Stale docs: ARCHITECTURE.md says 33 tools (real 84); references `lacerta-*.md` docs that don't exist in `docs/` | [measured] |
| H9 | Heal/alias layers exist because Ollama JSON mode lets the model drift (`args`→`arguments`, `file_path`→`path`, cap→tool mapping in `code_agent.py:41-113`) | [code] |
| H10 | Python-only deps with no drop-in C++ equivalent: `cloudscraper` (anti-bot), `chromadb` (on-disk format), `python-docx`, `markdownify`, PySide6 GUI, FastAPI | section 6 |
| H11 | Existing user data (SQLite `fact_graph.db`, Chroma `vector_db/`, `Agent-*` JSON ledgers) must be readable or migrated | [doc] ARCH §1, §7 |
| H12 | CUDA on Windows needs the MSVC host compiler. clang/llvm-mingw can't build the CUDA backend | [measured] llama build used cl.exe + nvcc |
| H13 | TSan is not available on Windows | section 2 corrections |
| H14 | The offline Python suite does not finish on this machine, so there's no complete green baseline yet. Run 1 (`-m "not live and not heretic and not qwopus"`, ai-agent-env) was killed after ~28 min at **15 GB working set**, with a QtWebEngine child. Run 2 (verbose) was stopped by choice at 49%: **450 passed, 13 failed**, and it was sitting on `tests/test_loop_web_scrape.py::test_loop_engine_calls_enrich_on_web_search` at 2.1 GB. The 13 failures are in test_agent_tools (2), test_capability_act_hints (2), test_character_build_ingest, test_config_catalog, test_implementation_plan, test_ledger_completion (2), test_light_research (2), test_loop_guards (2). Not diagnosed. They may come from the uncommitted work, the temp `AQUILA_DATA_ROOT`, or real bugs | [measured] 2026-11-02 |

---

## 8. Proposed C++ shape and port order [proposal, not started]

Order follows PDF R5 (data, then tools, then loop) and the repo's own reliability plan (code mode first, unified loop).

| Milestone | Scope | Proof of done |
|---|---|---|
| M0 | Branch/worktree, CMake + presets (MSVC+CUDA release, clang ASan/UBSan debug), FetchContent deps, CI | Clean configure+build on both presets; a deliberate leak test fails under ASan |
| M1 | Core value types: Message, ToolCall, ToolResult, Plan/Ledger, RunState JSON round-trip | Golden JSON fixtures exported from Python, byte-equal round-trip in C++ tests |
| M2 | `IInferenceBackend` + `OllamaHttpBackend` (parity with `OllamaClient.chat` non-stream + stream) | Same request payload as Python for fixed inputs (recorded fixtures); live smoke "pong" |
| M3 | 7 code primitives + path firewall (`is_safe_path`, `resolve_tool_path`) | Fixture repo: C++ output == Python output for a table of calls, incl. blocked paths |
| M4 | `AgentLoop` + `ContextCondenser` + `RuntimeTierConfig`; code mode end-to-end | Harness scenario `code_smoke_file` passes 3/3 on C++ (Python baseline today: 3/3 [doc]) |
| M5 | `LlamaCppBackend`: KV checkpoint/rollback (`llama_memory_seq_rm`), GBNF from schema | Post-wipe prefill token count measured < full prompt; grammar makes invalid JSON impossible in N trials |
| M6 | Modules + JSON recipe engine; port research/writing/learn/persona capabilities | Existing capability parity tests' scenarios, re-expressed as C++ tests |
| M7 | Memory: SQLite facts/scratchpad + vector index + embeddings | Reads existing `fact_graph.db`; recall@k on fixture matches Python within tolerance |
| M8 | Surfaces: CLI first, then GUI / Remote / MCP per decisions below | Per surface |

---

## 9. Open decisions (need the user)

Decided (2026-11-02, by user):

- **D1 Branch model: DECIDED.** Python changes committed and pushed on `Aquila-3.5` (`759212a`). `Aquila-cpp` is an **orphan** branch in a separate worktree (`F:\Users\myfri\Aquila-cpp`).
- **D2 Inference: DECIDED.** Ollama over HTTP first (M2-M4, parity), then direct llama.cpp with KV control (M5).
- **D4 llama.cpp source: DECIDED.** Upstream `ggml-org/llama.cpp`. Open follow-up: check whether the local fork's uncommitted Qwen 3.5 edits (section 1) are needed upstream.

Still open:

- **D3 GUI:** Port PySide6 → Qt6 C++ Widgets, keep the Python GUI as a client of the C++ core over a local API, or go CLI/Remote-PWA only at first?
- **D5 Plugin mechanism:** Is MCP stdio the R10 escape hatch, or should there be a separate `tools/plugins/manifest.json` scheme?
- **D6 Scope cut:** Which modes ship in the first C++ release (Code only? + Research? Character/Learn later?) Vision/data-processing out?
- **D7 Push Aquila-cpp:** Push the branch to GitHub now, or keep it local until M0 builds? (Making it the GitHub default branch is a separate choice.)

---

## Change log

| Date | Change |
|---|---|
| 2026-11-02 | Initial recon from `Aquila-3.5@0e51872` + dirty tree; PDF requirements R1-R17; hazards H1-H13; decisions D1-D6 |
| 2026-11-02 | Added H14 (partial test baseline; suite deferred per user) |
| 2026-11-02 | Pinned Python reference at `759212a` (H1 resolved); created orphan `Aquila-cpp` worktree; moved recon to `docs/recon/`; recorded D1/D2/D4; added local llama.cpp patch note and D7 |
