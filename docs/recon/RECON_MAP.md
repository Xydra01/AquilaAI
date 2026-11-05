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

C++ size for R20 (from the Aquila-cpp root; non-blank, non-`//` lines):

```bash
for d in src apps tests; do printf "%s: " $d; rg -v -c '^\s*(//.*)?$' $d --glob '*.{cpp,hpp,cu}' | awk -F: '{s+=$2} END {print s}'; done
# after M1 (incl. error_code): src 704, apps 41, tests 504
# after M2: src 1161, apps 41, tests 1109
# after M3: src 3979, apps 41, tests 2716
# after M4: src 4841, apps 41, tests 4451
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
| C++ toolchain present | MSVC BuildTools 2022 14.44 (`F:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`, not on PATH; use `scripts/msvc-dev.cmd`), clang 22.1.5 (llvm-mingw UCRT 20260505), CMake 4.3.2, Ninja 1.13.2, CUDA 13.2. **No clang-cl** (VS has only clang-format/clang-tidy) | [measured 2026-11-02] |
| Sanitizer runtimes | MSVC: ASan only (`clang_rt.asan_*`). llvm-mingw: ASan + UBSan. **No LeakSanitizer for any Windows target.** Leaks: CRT debug heap on MSVC Debug (non-ASan build), LSan on the Linux CI job | [measured] |
| Qt SDK | Qt **6.11.3** `msvc2022_64` at `F:\Qt\6.11.3\msvc2022_64` + qtwebengine, qtwebchannel, qtpositioning, qttasktree, via `scripts/install-qt.ps1`. aqtinstall 3.3.0 (latest release) can't read the Qt >= 6.11 repo layout; pinned to master `5a49f2b` (fix: miurahr/aqtinstall#1000) | [measured] |
| Qt style on 6.11.3 | `aquila_gui --smoke` on the real platform: `style=windows11`, keys `windows11,windowsvista,Windows,Fusion`. Offscreen platform falls back to `fusion` | [measured] |
| GPU | RTX 4070, 12282 MiB | [measured] |
| Existing llama.cpp | `tools/llama-cpp-turboquant` (fork `TheTom/llama-cpp-turboquant` @ `a62320c2c`, tracked as a gitlink with no `.gitmodules`), built with **MSVC cl.exe + nvcc, `GGML_CUDA=ON`** in `build-ninja/` | [measured: CMakeCache] |
| Local llama.cpp patches | The fork checkout has **uncommitted edits** in `common/arg.cpp`, `src/llama-model-loader.cpp`, `src/llama-model.cpp`, `src/models/qwen35.cpp`. Contents not reviewed. If they fix Qwen 3.5 loading, upstream may need the same fix (see D4) | [measured] |
| WSL | only `docker-desktop` distro (no Ubuntu) | [measured] |
| Ollama server | **Stock 0.40.14** at `F:\Users\myfri\AppData\Local\Programs\Ollama` (upgraded 2026-11-03; installer SHA256 `e069c7cc…` = GitHub digest), serving `127.0.0.1:11434`, 18 models, CUDA on the RTX 4070. The app's auto-update is **off** (`auto_update_enabled = 0` in `AppData\Local\Ollama\db.sqlite`) and `agent-projects\tools\ollama-turboquant` was **removed from the user PATH** (backup: `Downloads\aquila-tmp\user-path-backup.txt`); see H16. The turboquant build (`pr15505-turboquant`) is old and buggy (user) and is not a test target | [measured] |
| `aquila:latest` | Same weights blob as `qwen3.5:9b`, stock `qwen3.5` renderer/parser; Modelfile sets `temperature 0.2`, `top_k 20`, `top_p 0.95`, `num_ctx 32768`, `presence_penalty 1.5`. Because of H15 every Python request ran at 0.2 | [measured] `ollama show --modelfile` |

**Implication:** "parity with Python" means parity with `759212a`. If the Python branch moves on, either re-pin here (and rerun the inventory) or check out `759212a` for parity work.

### C++ dependencies (pinned in `cmake/AquilaDeps.cmake` by URL + SHA256)

| Library | Version | Archive |
|---|---|---|
| nlohmann/json | 3.12.0 | release asset `json.tar.xz` |
| fmt | 12.2.0 | release asset `fmt-12.2.0.zip` (spdlog uses it via `SPDLOG_FMT_EXTERNAL`) |
| spdlog | 1.17.0 | tag archive |
| inja | 3.5.0 | tag archive (uses the fetched nlohmann/json, not its embedded copy) |
| cpp-httplib | 0.64.0 | tag archive; OpenSSL/zlib/brotli/zstd off. Requires Windows 10 (`_WIN32_WINNT=0x0A00`) |
| Catch2 | 3.16.1 | tag archive |
| RapidCheck | commit `2c3c436` (2026-10-05; no upstream releases) | commit archive; built by `cmake/AquilaRapidCheck.cmake` with `RC_ENABLE_CATCH` left OFF (its `ext/catch` submodule is absent from the archive) and the `extras/catch` header exposed via an own `rapidcheck_catch` INTERFACE target with SYSTEM includes so its templates stay out of `/W4 /WX` and `-Werror`. Linked into `aquila_unit_tests` only. [measured: builds clean on mingw-san (clang ASan+UBSan -Werror) and msvc-release] |
| tree-sitter (core) | 0.27.1 | tag archive; `lib/src/lib.c` amalgamation built by `cmake/AquilaTreeSitter.cmake` (upstream build scripts unused) |
| tree-sitter-c / -cpp / -python | 0.24.2 / 0.23.4 / 0.25.0 | tag archives; grammar ABI 15 / 14 / 15 (core accepts 13-15). The C++ `parser.c` is 25 MB: about 90-120 s per cold lane build. UBSan's `-fsanitize=function` is off for these C targets only (upstream scanner prototype mismatch) |
| llama.cpp (M5) | upstream `ggml-org/llama.cpp` tag **b12116** | tag archive, SHA256 `a73304d8...9a45f5`, built by `cmake/AquilaLlamaCpp.cmake` (libs `llama` + `llama-common`; CUDA on MSVC sm_89, CPU elsewhere; subtree forced to C++17; our sanitizer/warning flags scoped OFF upstream targets). Loads Qwen 3.5 and Llama unpatched (D4 verified) |
| test/base model GGUFs (M5) | stories15M-q4_0 (tiny, CI) `66967fbe...1861739`; Qwen3.5-4B-Q4_K_M `bf37767f...eb001d`; **Llama-3.2-3B-Instruct-Q4_K_M `6c1a2b41...728ff`** and **Meta-Llama-3.1-8B-Instruct-Q4_K_M `7b064f58...3557c`** (bartowski, the D15 base pair) | pinned by URL+SHA256; tiny fetched for unit tests, the larger ones opt-in behind `AQUILA_LIVE_TESTS`, local copies on D: preferred |

### Building

| Lane (preset) | Toolchain | What it proves |
|---|---|---|
| `msvc-release` | cl, Release, Qt | Release build + GUI smoke; `sanitizer.report` = `asan=0` |
| `msvc-asan` | cl, Debug, `/fsanitize=address`, Qt | ASan heap-overflow / use-after-free; CRT leak report from a non-ASan build of the same source |
| `msvc-release-cuda` | cl + nvcc, sm_89 (local only) | CUDA host-compiler path (H12); WebEngineWidgets CMake package present |
| `mingw-san` | llvm-mingw clang, Debug, ASan + UBSan (no Qt) | ASan + UBSan signed overflow |
| `linux-san` | clang (CI), Debug, ASan + UBSan + LSan (no Qt) | Everything above that is portable + LeakSanitizer |

```bash
# MSVC lanes (from bash; cmd.exe drops the doubled backslashes)
export QT_ROOT_DIR='F:\Qt\6.11.3\msvc2022_64'
cmd //c "scripts\\msvc-dev.cmd cmake --workflow --preset msvc-release"
cmd //c "scripts\\msvc-dev.cmd cmake --workflow --preset msvc-asan"
cmd //c "scripts\\msvc-dev.cmd cmake --workflow --preset msvc-release-cuda"
# llvm-mingw lane (clang++ from llvm-mingw on PATH)
cmake --workflow --preset mingw-san
```

CI: `.github/workflows/ci.yml` runs `windows-msvc` (msvc-release + msvc-asan, qtbase only), `windows-mingw-san`, `linux-san` on every push to `Aquila-cpp`.

Live tests (need the stock Ollama server; never in CI). They refuse to run unless `/api/version` is a plain release number:

```bash
cmd //c "scripts\\msvc-dev.cmd cmake --preset msvc-release -B build/live -DAQUILA_LIVE_TESTS=ON -DAQUILA_BUILD_GUI=OFF"
cmd //c "scripts\\msvc-dev.cmd cmake --build build/live --target aquila_live_tests"
./build/live/tests/live/aquila_live_tests.exe     # AQUILA_LIVE_MODEL overrides aquila:latest
```

---

## 2. Design brief, distilled into requirements

Source: `docs/design/aquila-cpp-design.md` (byte-identical copy of the user's `Aquila cpp.md`, sha256 prefix `5df25a1814eba1e7`). `D:Lnn` = line in that file.

The doc is a conversation that **evolves**. Earlier sections float ideas that later sections refine or replace. Section 2.1 is what governs; section 2.2 records what was superseded, so nobody builds from the earlier version by mistake.

### 2.1 Governing requirements (the doc's final position)

| ID | Requirement | Source |
|---|---|---|
| R1 | Strict C++20: zero raw owning pointers; `unique_ptr`/`shared_ptr`/RAII | D:L13 |
| R2 | **Single-threaded, deterministic, value-oriented core loop.** All data owned by `ContextCondenser` or the `AgentLoop` frame; pass by `const T&` / `std::move`. No async, no coroutines | D:L58-61, D:L212-217 (supersedes S1) |
| R3 | FetchContent / header-only deps: nlohmann/json, cpp-httplib, spdlog+fmt, inja (still needed for `{{...}}` in recipe cartridges, D:L435, D:L443) | D:L42-51, D:L346 |
| R4 | Sanitizers in debug builds from day one | D:L53 |
| R5 | Port module-by-module with Python as the reference spec: data structures → execution sandbox → orchestration loop | D:L57 |
| R6 | **Context condenser with 3 KV segments:** `[0..P]` system prompt **+ active recipe schema** (never evicted); `[P+1..S]` structured scratchpad **+ module state snapshots** (evicted only on wipe); `[S+1..end]` rolling tail of the last 2-3 tool/action results | D:L63-75, refined D:L572-578 |
| R7 | Self-note is a **strict schema** (e.g. `current_hypothesis`, `verified_facts`, `failed_approaches_do_not_repeat`, `next_immediate_action`), forced by grammar during condensation | D:L201-204 |
| R8 | Pre-truncate oversized outputs before they enter the rolling tail (head+tail), spill the full output to a side buffer with a reference | D:L206-210 |
| R9 | **Coarse-grained, stateful modules ("cartridges"), 4-6 of them,** are the LLM-facing unit. Each owns its domain state in C++ memory, exposes a few high-level actions, has built-in guardrails and recovery, and survives context wipes. This replaces the "flat bag of functions" and "tiny Unix-like primitives" designs | D:L350-364 (supersedes S2) |
| R10 | `IAgentModule` interface: `module_id`, `get_actions → ActionSchema[]`, `execute_action → ActionResult{success, llm_facing_output, token_estimate}`, `export_state_snapshot` / `restore_state_snapshot` | D:L366-411 |
| R11 | Four core modules (state / actions / behind-the-scenes work): **WorkspaceModule** (file buffers, RAM backups, file tree; `inspect_symbol`, `surgical_edit`, `revert_file`; rejects conflict markers/unbalanced braces), **ExecutionModule** (env, cwd, PIDs, stdout/stderr ring; `run_build_and_diagnose`, `run_test_suite`, `exec_sandboxed_cmd`; dedups logs → top 5 error blocks), **KnowledgeModule** (SQLite/vector, cached pages/docs; `search_local_docs`, `fetch_and_clean_url`, `store_fact`; HTML strip, markdown chunking, caching), **OrchestratorModule** (condenser ref, recipe checklist, step counter; `checkpoint_notes`, `trigger_context_condense`, `complete_recipe`; validates scratchpad fields before a wipe) | D:L414-423 |
| R12 | **Recipes are user/agent-created "Configuration & Workflow Cartridges"**: `goal_template`, `load_modules[{module, initial_state, expose_actions}]`, `pre_llm_hooks`, `scratchpad_checklist`, `post_llm_validation_hook{must_succeed, on_failure_instruction}`. They do **not** pipe raw strings between primitives. Exposed surface is 3-4 actions per task. The loop refuses to exit while the validation hook fails | D:L221, D:L425-484, D:L539, D:L757 (supersedes S3, S4) |
| R13 | Module registry: **Option A compile-time** (`registry.register_module<T>(id)`, single binary) as the default. Option B (DLL/.so plugins via C factory) optional | D:L486-522 |
| R14 | LLM action call = grammar-enforced JSON `{"thought": <1-2 sentences>, "module", "action", "args"}`, ~45 tokens | D:L590-608 |
| R15 | `IInferenceBackend`, KV-aware, **linked directly against the C/C++ inference API** (not HTTP per turn): `append_to_kv_cache`, `mark_kv_checkpoint`, `rollback_kv_to`, `generate_structured(gbnf, max_tokens, ngram)`, `ComputeProfile {GPU_HIGH_VRAM, CPU_MOE_FAST, CPU_LOW_SPEC_EDGE}` | D:L569-573, D:L617-668 |
| R16 | **CPU-first ("console-first") design**, with the GPU as boost. One code path; `RuntimeTierConfig` universal flags (KV rollback, GBNF, n-gram) + tier knobs: condense threshold 2048/6144, rolling tools 2/4, tool output chars 1500/4500, thought tokens 45/150, gpu layers 0/999 | D:L669-672, D:L706-734 (supersedes S6) |
| R17 | CPU engine discipline: repacked quants, BLAS for prefill, physical-core (P-core) pinning (`physical - 1`), n-gram prompt-lookup speculation | D:L543-562, D:L609-615 |
| R18 | Model: **Qwen 3.5 family**, read as Route 2: 4B for the CPU base (`q4_0_4_8`), 9B Q6_K/Q8_0 for the 4070 boost, 0.8B as the draft model | D:L759-791 [interpretation: D:L791 says only "Qwen 3.5 family idea"; Route 1 also offers Qwen 3.5 4B everywhere] |
| R19 | **Improve, don't transliterate.** Python is the behavioral reference, not the shape to copy. A C++ design may diverge from Python *only* when it fixes a concrete Python problem, and the divergence is recorded with the Python evidence (file:line) it fixes. Where Python got something right, keep it (example: `ActionResult.error_code`, section 8.1) | user, 2026-11-03 |
| R20 | **Condense.** Same behavior in less code: one type per concept, one format per exchange (e.g. one action-call format instead of two), no compatibility layers the new design makes unnecessary (heal/alias layers H9, facade re-exports H2, dead paths H5). Measured per milestone: C++ LOC added in `src/` + `apps/` (non-blank, non-comment) vs the non-test Python LOC it replaces (PY_INVENTORY). When C++ is not smaller, the milestone row says why | user, 2026-11-03 |

### 2.2 Superseded or evolved within the doc (do NOT build these as written)

| ID | Earlier idea | Where | Replaced by |
|---|---|---|---|
| S1 | 1-3 OS threads (orchestrator / GPU worker / tool worker) with a mutex+condvar `TaskQueue` | D:L17-32, D:L55 | R2 single-threaded core. Remaining parallelism lives *inside* the inference backend (llama.cpp's own compute threads, R17) [interpretation] |
| S2 | ~10-15 **atomic primitives** (`fs_read`, `bash_exec`, `regex_extract`, `llm_subprompt`...) as the LLM-facing tool surface | D:L221-232 | R9-R11 modules. Primitive-level work (file I/O, process spawn, regex, HTML strip) becomes **internal implementation inside modules** ("Automatic Behind-the-Scenes C++ Work", D:L418) [interpretation: the doc never says primitives disappear internally] |
| S3 | Primitive-piping recipe format: `steps[{primitive, args, on_failure, condition}]` + `output_template` (e.g. `bash_exec → regex_extract → llm_micro_pass`) | D:L253-302 | R12 cartridge format. "A Recipe no longer needs to micro-manage low-level string piping" (D:L427) |
| S4 | `IToolPrimitive` interface; `RecipeRunner` implemented *as* a composite tool, recipes nesting recursively | D:L330-343 | R10 `IAgentModule` + R12 cartridges. Nesting/recursion is not carried forward (open, see D9) |
| S5 | Condenser example with fixed `max_recent_tools_ = 3`, `token_wipe_threshold_ = 6144` | D:L115-116 | R16 tier-scaled values |
| S6 | Condenser segments = system prompt / self-notes / tail | D:L63-75 | R6 refined: prefix also pins the **active recipe schema**, the anchored block also carries **module state snapshots** (D:L576-577) |
| S7 | `llama_kv_cache_seq_rm(ctx, 0, P+1, -1)` | D:L571, D:L583 | **Factual correction, CONFIRMED against upstream b12116 at M5.** The current API is `llama_get_memory(ctx)` + `llama_memory_seq_rm(mem, seq, p0, p1)` / `llama_memory_seq_pos_max`; verified against the header actually built (`_deps/llamacpp-src/include/llama.h`), not the old turboquant fork. M5's `LlamaSession::rollback_to` uses exactly this. Caveat: on recurrent/M-RoPE models (Qwen 3.5) a mid-sequence `seq_rm` does not rewind recurrent state (finding F1, section 8.5) [measured 2026-11-05] |

**Ideas the doc left open, now settled by the user (2026-11-02):**

- **Escape hatch 1, plugin scripts + `manifest.json`** (D:L308-316): **KEPT (D5).** Reframed for modules [proposal]: each `tools/plugins/<name>/manifest.json` declares a *script module* (id, actions with JSON input schemas, command per action). A `ScriptModule` adapter implements `IAgentModule` over it, running JSON on stdin and reading the result from stdout, so recipes load it like any compiled module.
- **Escape hatch 2, `register_new_recipe`** (D:L318-324): **KEPT (D9)**, reframed: the agent saves a *cartridge* (modules + exposed actions + hooks + checklist), not a primitive sequence.
- **`llm_micro_pass`** (D:L283-289, D:L302): **KEPT (D9)**, reframed [proposal]: a hook type usable in `pre_llm_hooks` / post hooks that runs one isolated LLM call (own system prompt, no main-context or KV pollution) and injects only its output.
- **Recipe nesting** (from S4): **KEPT (D9)** [proposal]: a cartridge may `include` another cartridge's modules/hooks/checklist.
- **How users author recipes** (D:L348): **GUI builder (D8).** The doc's "no-code tool maker" trap (D:L239) is about building *tools*; a builder that edits cartridge *configuration* is the option the doc itself lists at D:L348. Planned with QtNodes (`GUI_EVALUATION.md` F2). The Architect Agent is noted as a later idea.
- **Sandboxed scripting (sol2/Lua)** as a "Phase 2 upgrade if recipes hit a ceiling" (D:L238): still deferred.

**Other checks against local source:**

- llama.cpp ships `json_schema_to_grammar(nlohmann::ordered_json)` (`common/json-schema-to-grammar.h:9`), so R14 action schemas can be generated as JSON Schema and turned into GBNF. [measured]
- R4 on this machine: TSan is not available for Windows targets. Under R2 (single-threaded) TSan matters much less; it's only needed if a UI/IO thread is added at the edge. MSVC has ASan but no UBSan, and no Windows toolchain has LeakSanitizer. [measured at M0: see section 1 "Sanitizer runtimes"]
- R2 vs today's Python: the agent runs on a Qt worker thread with a cross-process generation lock (`agent/core/generation_lock.py`). [proposal: single-threaded core; any GUI/remote surface talks to it from outside the core]
- R15 vs decision D2 (Ollama first): Ollama exposes no KV control, so an Ollama backend **cannot** satisfy R6/R15 KV pinning. The Ollama phase is a parity scaffold. `IInferenceBackend` must be designed for KV ops from day one, with the Ollama implementation degrading those ops to resending the full prompt.

---

## 3. Python codebase at a glance

[measured at `759212a`, see PY_INVENTORY.md] 466 `.py` files, 78,483 LOC. Non-test 255 files / ~59.8k LOC; tests 211 files / 18,678 LOC.

| Package | Files | LOC | Role | C++ disposition [proposal] |
|---|---:|---:|---|---|
| `agent/core` | 36 | 22168 | Brain: Ollama client, Agent, loop engine, planner, prompts, tools firewall, MCP, harness | Split; rewrite loop; see section 4 |
| `agent/gui` | 29 | 9052 | PySide6 desktop app, 9 workspaces | Qt 6 Widgets in C++ (D3 decided, `GUI_EVALUATION.md`); canvas expanded (D10); recipe builder (D8) |
| `agent/tool_library` | 20 | 4191 | 74 tools merged into `ALL_TOOLS` | Absorbed into the 4 core modules as internal code + a few exposed actions each (R9-R11); see section 5.1 |
| `agent/storage` | 15 | 3984 | SQLite facts, Chroma vectors, instances, personas, learn, settings | Port (SQLite C API + vector index) |
| `agent/policies` | 15 | 3719 | Context budget/tiers, tool catalogs, step policies, think policy | Becomes `RuntimeTierConfig` (R16) + `ContextCondenser` (R6) + recipe `expose_actions` scoping (R12) |
| `agent/capabilities` | 57 | 3266 | 44 versioned capabilities (Pydantic in → `CapabilityResult`) | Batched behavior becomes module actions (R10/R11). Per-mode step policies become recipe cartridges (R12) |
| `agent/remote` | 13 | 2963 | FastAPI + WS server (52 routes) for PWA `webapp/` | Rebuild in C++, keep the HTTP/WS contract so `webapp/` keeps working (D6) |
| `agent/parser` | 8 | 2656 | Strict schema builder, JSON parse/heal, Ollama diagnostics | Replace with nlohmann/json + schema → GBNF |
| `agent/research` | 10 | 1731 | Web enrichment, URL registry, content quality, light research | Port into KnowledgeModule (R11) |
| `agent/coding` | 7 | 1250 | File parser (PDF/DOCX/images), language registry, light coding | Port; PDF via MuPDF C |
| `agent/aquila_runtime` | 12 | 1170 | Hardware detection, Ollama/Docker/SearXNG bootstrap, paths | Port `hardware_profile` → `ComputeProfile` |
| `agent/functions` | 9 | 870 | Recipes (intent → capability list), writing brief/scope | Replace with recipe cartridges (R12) |
| `agent/vision` | 6 | 779 | torch CNN classifier (experimental) | **Out (D6).** Only imported by `agent/tasks/data_processor.py` [measured], so it leaves with data processing |
| `agent/tasks` | 1 | 243 | Headless data processor | **Out (D6):** data processing mode is being rethought |
| `agent` (`agent/__init__.py`) | 1 | 120 | Legacy import aliases (`import main`, ...) | Drop |
| `scripts` | 3 py + 40 sh/ps1 | 994 (py) | Health check, Ollama install/serve, harness gate, packaging preflight | Keep as tooling; C++ build adds its own |
| `tests` (root) | 6 | 570 | Vision calibration scripts | Out of scope |
| `new_project` | 7 | 79 | Sample "galaga" project (agent output fixture) | Ignore / possible harness fixture |

### 3.1 Tool, capability, and recipe surfaces [measured]

- **Legacy tools:** `SURVIVAL_TOOLS` (10) + `ALL_TOOLS` (74) = 84, no overlap. (`ARCHITECTURE.md` §8 says 33, which is stale.)
- **Code-mode tool surface** (`agent/policies/code_tool_catalog.py`): `find_files, grep, list_dir, read_file, run_command, search_replace, write_file` (7), the stateless flat-tool style the design doc moves away from (S2). In C++ these become *internal* operations of WorkspaceModule / ExecutionModule, and their Python outputs serve as the parity oracle for those modules (section 5.1).
- **Capabilities** (44): dev 12, research 10, writing 6, learn 5, plan 5, persona 4, web 2. Shape: `CapabilitySpec{id, version, input_model, handler, tier, modes}` (`agent/capabilities/registry.py:13-21`). Handler signature: `(CapabilityContext, BaseModel) -> CapabilityResult` (`agent/capabilities/base.py:100`). These are batched but **stateless**: state lives in JSON files on disk, not in the capability.
- **Recipes** (15): `agent/functions/recipes.py`, just `recipe_id → tuple[capability_id]`. No modules, exposed-action scoping, hooks, checklist, or validation gate. R12 cartridges replace these entirely.

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

**Current direction in the repo** (`docs/reliability-plan/README.md`) [doc]: "One dumb loop, sharp tools, batched capabilities." Phases 0-3 are marked done, and Phase 4 (unified ~300-line `agent_loop.py`) is not started. Code mode already bypasses `LoopEngine` (`loop_engine.py:187-191` raises for `mode=code`). The *loop shape* lines up with the design doc (one simple deterministic loop, R2), so the C++ `AgentLoop` should take its turn mechanics from `code_agent.run_tool_session`, *not* from `LoopEngine`. The *tool shape* does not line up: the Python code loop calls flat stateless tools, while the doc calls for stateful modules (R9).

**Scope note (user, D10):** the reliability plan's move *away from Code Canvas* to direct filesystem tools was made for the successor framework **Lacerta**, not for Aquila. That's also why the plan links `lacerta-*.md` docs that aren't in this repo (H8). Aquila keeps and expands the canvas. So for Aquila-cpp the reliability plan informs the *loop* (simple, harness-gated) but not the *edit model*.

---

## 5. Concept crosswalk: design doc vs. existing Python

| Design concept (governing) | Closest Python today | Gap / note |
|---|---|---|
| Coarse-grained stateful modules (R9, R10) | Nothing is both stateful and LLM-facing. **Batched behavior:** capabilities (`agent/capabilities/`), stateless functions. **State:** JSON buffers on disk (`Agent-Code/active_code_state.json` via `code_canvas_tools.py`, `Agent-Drafts/active_draft_state.json` via `writing_tools.py`). **Snapshots:** `run_state_providers.py` ground-truth providers (≈ `export_state_snapshot`) | Core design shift. Merge "batched behavior + domain state + snapshot" into one C++ object per domain. Section 5.1 maps the 4 modules |
| Recipe cartridges (R12) | `agent/functions/recipes.py` (intent → ordered capability IDs); per-step allowlists in `agent/policies/tool_catalog.py` / `step_policies.py` / `capabilities/adapters.py` (≈ `expose_actions`); plan checklist `cap.plan.update_checklist@v1` (≈ `scratchpad_checklist`) | Python spreads one cartridge's worth of information across 4+ files and the planner. No `pre_llm_hooks`; no `initial_state` |
| `post_llm_validation_hook` exit gate (R12) | TDD soft gates in `loop_engine.py` ([doc] ARCH §17); `agent/core/harness_gate.py` (offline gate only) | Make it a loop invariant: the loop cannot exit while `must_succeed` fails |
| Action call `{thought, module, action, args}` (R14) | Code mode: `{reasoning, tools[{name, arguments}], final_report}`; capability modes: `{reasoning, capabilities[{id, arguments}]}` (`docs/capability-modules-vision.md` "Act-turn JSON") | Two formats today → one. `thought` capped (R16 `max_thought_tokens`). Heal/alias layers (`heal_calls.py`, `code_agent.py:41-113`) should become unnecessary under a grammar |
| `ContextCondenser`, 3 KV segments (R6) | `agent/policies/context_manager.py` (`build_loop_messages`, `on_step_advance`, `compress_step_transcript`), `agent/policies/context_budget.py` | Python wipes history on step advance ([doc] ARCH §5.5) and LLM-summarizes. No rolling-K tail as a structure; no module-snapshot segment; no pinned recipe schema |
| Strict self-note schema (R7) | `agent/core/run_state.py` `TaskRunContext` (goal, goal_summary, run_digest, checklist, milestones, ground_truth); scratchpad notes via `save_research_note` | Digest is free text, and notes are not schema-enforced. OrchestratorModule must validate required fields (R11) |
| Pre-truncate + spill (R8) | `agent/policies/code_context.py` `truncate_text` / `tool_output_max_chars`; `format_capability_result_for_llm` 12k cap (`agent/capabilities/base.py:66-97`) | Head-only truncation; no spill buffer + reference |
| `IInferenceBackend` direct, KV-aware (R15) | `OllamaClient` (`agent/core/main.py:273-1430`), HTTP `/api/chat` with a JSON-schema `format` | No KV control is possible through Ollama. D2 makes Ollama a parity scaffold only (see section 2.2 checks) |
| GBNF (R7, R14) | `agent/parser/structured_schema.py` (980) builds Ollama JSON schemas | Generate JSON Schema from `ActionSchema`s of the *exposed* actions → `json_schema_to_grammar` |
| `RuntimeTierConfig` / `ComputeProfile` (R16) | `ContextProfile` tiers keyed on `num_ctx` (`agent/policies/context_budget.py:9-71`); `HardwareProfile` presets (`agent/aquila_runtime/hardware_profile.py:17-28`); `model_tiers.py`, `thinking_tiers.py` | Python keys on context size, the doc keys on hardware and is CPU-first. Rebuild around `ComputeProfile` |
| Module registry Option A (R13) | `agent/capabilities/registry.py` (`register_capability`, import-time `_register_all`) | Same idea; becomes `register_module<T>()` |
| Harness as proof | `agent/core/capability_harness.py` scenarios + `scripts/harness_gate.sh` | Reuse the scenarios as cross-language acceptance tests |

### 5.1 The four core modules (R11) and where their Python behavior lives

These are parity oracles and starting points, not 1:1 ports. [code]

| Module | Doc actions | Python sources of behavior/state | Notable gap vs doc |
|---|---|---|---|
| **WorkspaceModule** | `inspect_symbol`, `surgical_edit`, `revert_file` | Code Canvas (in-memory project buffer, `pending_patches` accept/reject): `agent/tool_library/code_canvas_tools.py` (`read_code_outline:447`, `replace_symbol:640`, `apply_unified_patch:570`, `replace_lines:541`, patches `:144-175`). Direct FS tools: `agent/tool_library/code_agent_tools.py` (`read_file:38`, `write_file:87`, `search_replace:137`, `list_dir:189`, `grep:201`, `find_files:209`). Path firewall: `agent/core/tools.py` (`is_safe_path`, `resolve_tool_path`). Symbols: `git_tools.find_references:66` **D10 decided: canvas buffer model.** Edits land in RAM buffers as pending patches, get validated (rollback on bad syntax, per the doc), then are accepted and synced to disk. **Code Canvas (`code_canvas_tools.py`) is the primary parity oracle**; the direct FS tools are secondary. Python's `write_file` keeps broken edits (`code_agent_tools.py:128-131`); the C++ module must not |
| **ExecutionModule** | `run_build_and_diagnose`, `run_test_suite`, `exec_sandboxed_cmd` | `agent/tool_library/run_tools.py` (`run_command:38`), `shell_tools.run_terminal_command:65`, `agent/coding/language_registry.py` (`run_linter:82`, `run_tests:192`), `code_canvas_tools.run_pytest:879`, `agent/core/code_run_diagnostics.py` | Python returns truncated raw output. The doc dedups logs and returns the top 5 error blocks. No persistent env/PID/ring-buffer state |
| **KnowledgeModule** | `search_local_docs`, `fetch_and_clean_url`, `store_fact` | `agent/storage/memory.py` (SQLite facts + Chroma), `agent/storage/embeddings.py`, `agent/tool_library/web_tools.py` (`web_search:48`, `read_webpage:129`), `agent/research/*` (enrichment, content quality, URL registry), `agent/storage/learn_index.py`, `agent_tools.store_fact:27` / `query_past_experience:23`, `coding_tools.semantic_code_search:138` | Python has no local page cache layer equivalent to "repeated lookups cost zero network I/O". Chroma needs a C++ replacement (H10) |
| **OrchestratorModule** | `checkpoint_notes`, `trigger_context_condense`, `complete_recipe` | `agent/core/run_state.py` (`TaskRunContext`, `checkpoint_capability`), `agent/policies/context_manager.py`, `agent/core/implementation_plan.py` + `cap.plan.update_checklist@v1`, `agent_tools.checkpoint_step:177` / `save_research_note:79`, `agent/core/tools.py` (`mark_objective_complete:453`, `finish_task:460`) | Python doesn't validate required scratchpad fields before a wipe. The step-advance wipe is triggered by the planner/loop, not by the module |

### 5.2 Additional modules (D11: approved 2026-11-02; action lists are still sketches)

The doc's four modules cover code, execution, knowledge, and meta. Aquila also has writing, Character AI, and Learn, each of which owns **persistent domain state**, which is exactly what R9 says belongs in a module rather than in the LLM's context.

| Proposal | What it owns | Actions (sketch) | Why a module, not just a recipe | Python sources |
|---|---|---|---|---|
| **Shared `CanvasBuffer` core** (a library, not a module) | In-RAM documents, versioned edits, pending patches, anchored selections (`{doc, range, text, context}`), undo/redo, diff | n/a (used by Workspace + Document) | D10 wants the *same* Gemini-style live-edit experience for code and writing. One buffer engine serves both modules and the GUI canvas, so the GUI just renders buffer events | `code_canvas_tools.py` (buffer + `pending_patches`), `agent/coding/writing_canvas.py`, `writing_tools.py`, selection subcalls `code_ide_page.py:263` / `writing_page.py:521` |
| **DocumentModule** (writing canvas) | Active draft, outline/sections, sources attached, compile state | `outline`, `draft_section`, `revise_selection`, `compile_document` | Writing has its own structure (sections, outline, compile) that code doesn't; today it lives in `Agent-Drafts/active_draft_state.json` and 6 `cap.writing.*` capabilities | `writing_tools.py`, `capabilities/writing/*`, `functions/writing*.py` |
| **PersonaModule** (Character AI) | Active persona bible, user prefs, chat history, build state | `load_persona`, `write_initialization`, `update_preferences`, `finalize_persona` | Persona state must survive context wipes and stay out of the rolling tail. In-character chat temperature/prompting is persona-owned | `storage/persona_registry.py`, `tool_library/persona_tools.py`, `capabilities/persona/*` |
| **LearnModule** (Classroom + Archives) | Course/syllabus, mastery tiers, assessment results, archive index handle | `write_syllabus`, `generate_assessment`, `record_result`, `set_mastery_tier`, `search_archive` | Mastery/assessment state is long-lived and per-course; retrieval uses KnowledgeModule underneath | `storage/learn_registry.py`, `storage/learn_index.py`, `tool_library/learn_tools.py`, `capabilities/learn/*` |

Research stays a **recipe cartridge** over Knowledge + Document (+ Orchestrator); it has no state of its own beyond sources and notes, which KnowledgeModule already owns.

Count: 4 core + 3 domain = **7 modules**, one over the doc's "4 to 6" (D:L352); approved as-is by the user.

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
| H13 | TSan is not available on Windows (lower impact under R2 single-threaded) | section 2.2 "Other checks" |
| H14 | The offline Python suite does not finish on this machine, so there's no complete green baseline yet. Run 1 (`-m "not live and not heretic and not qwopus"`, ai-agent-env) was killed after ~28 min at **15 GB working set**, with a QtWebEngine child. Run 2 (verbose) was stopped by choice at 49%: **450 passed, 13 failed**, and it was sitting on `tests/test_loop_web_scrape.py::test_loop_engine_calls_enrich_on_web_search` at 2.1 GB. The 13 failures are in test_agent_tools (2), test_capability_act_hints (2), test_character_build_ingest, test_config_catalog, test_implementation_plan, test_ledger_completion (2), test_light_research (2), test_loop_guards (2). Not diagnosed. They may come from the uncommitted work, the temp `AQUILA_DATA_ROOT`, or real bugs | [measured] 2026-11-02 |
| H15 | **Python's temperature never applied.** `_build_native_chat_payload` puts `temperature` at the top level of `/api/chat` (`agent/core/main.py:808`); Ollama's `ChatRequest` has no such field (it lives in `Options`, `api/types.go:586`) and drops it. Every call (0.0-0.6 at 18 sites) ran at the model default, 0.2 for `aquila:latest`. C++ sends `options.temperature` (section 8.2). Proven live on stock 0.40.14: top-level 0.0 and 2.0 give byte-identical output equal to `options.temperature 0.2`; options 0.0 and 2.0 differ | [measured] 2026-11-03 |
| H16 | **Two Ollama desktop-app bugs** (v0.40.14 source). (1) At startup it applies any staged update without a version check (`app/cmd/app/app.go:399-420`): it replaced a fresh 0.40.14 install with a staged 0.40.13. (2) It looks for its server as `ollama` (no `.exe`) in its own folder, so the check fails on Windows and it falls back to `exec.LookPath` (`app/server/server.go:54-84`): with the turboquant folder first on PATH, the stock app started the turboquant server. Worked around (section 1 "Ollama server"); any terminal started before the PATH change still has the old order | [measured] 2026-11-03 |
| H17 | **CUDA context/VRAM leak on repeated create/destroy [POST-M5 FOLLOW-UP].** Running the live/bake-off suite repeatedly (many `LlamaCppBackend` ctor/dtor cycles, plus force-killed runs) exhausts VRAM: a ~520 MiB compute-buffer `cudaMalloc` fails while `nvidia-smi` still reports ~10 GB free, reproducing even on known-good committed code; a GPU reset clears it. The RAII wrappers free `llama_model`/`llama_context`, but a per-process CUDA context / allocator reservation is not reclaimed between backends on Windows. Not an M5 blocker (single runs + the 4B CPU / 9B GPU verdicts are clean after a reset). FIX AFTER M5: reuse one model+backend across the suite instead of reconstructing per strategy, and/or call a CUDA context teardown between runs; add a leak check to the live harness. [observed 2026-11-05] |

---

## 8. Proposed C++ shape and port order [proposal, not started]

Order follows R5 (data structures → execution sandbox → orchestration loop), with modules as the unit (R9). Code/workspace work comes first because it's the best-tested Python path. All single-threaded (R2).

| Milestone | Scope | Proof of done |
|---|---|---|
| M0 | CMake + presets (5 lanes, section 1 "Building"), FetchContent deps pinned by SHA256, CI. Qt 6.11.3 MSVC SDK (+WebEngine) installed | Clean workflow-preset run on every lane; a tampered `URL_HASH` fails configure; deliberate heap-overflow / use-after-free / signed-overflow tests match the sanitizer's report text; leaks are caught by LSan (Linux CI) and the MSVC CRT debug heap (the original "leak test fails under ASan" isn't possible on Windows: no LSan); `aquila_gui --smoke` builds, links, runs; CUDA vector_add on the 4070 with a negative control. **Done 2026-11-02** |
| M1 | Core value types: Message, `ActionSchema`, `ActionResult`, `ToolInteraction`, `AgentScratchpad` (R7 schema), recipe cartridge struct (R12), JSON round-trip | Golden JSON fixtures, byte-equal round-trip; recipe JSON from D:L433-477 parses and re-serializes. **Done 2026-11-03** (section 8.1): 17 golden fixtures byte-equal (6 generated by Python at `759212a`); the recipe and action-call blocks are read from the design doc at test time; strict-rejection and byte-deletion tests run on all sanitizer lanes and CI |
| M2 | `IInferenceBackend` (KV ops in the interface from day one) + `OllamaHttpBackend` (parity scaffold; KV ops degrade to resending the full prompt) | Same request payload as Python for fixed inputs (recorded fixtures); live smoke "pong". **Done 2026-11-03** (section 8.2): 7 payloads from Python's real `_build_native_chat_payload` match except exactly `/temperature → /options/temperature` (H15); fake-server tests for every error code, streaming reassembly, stall timeout, cancel, KV rollback; live pong (plain, schema, stream) and the temperature proof on stock 0.40.14. R20: 457 C++ lines vs 644 Python (`main.py:732-1430`), part of which is deferred rather than condensed |
| M3 | `IAgentModule` + compile-time `ModuleRegistry` (R13) + **`CanvasBuffer` core** (5.2) + **WorkspaceModule** (canvas buffer model, D10) and **ExecutionModule** (log dedup) with the path firewall | Fixture repo: results checked against Code Canvas outputs (`code_canvas_tools.py`) where behavior overlaps; a bad edit is rejected and both buffer and disk are untouched; pending patch accept → sync writes exactly the diff; `export → restore` snapshot round-trip. **Done 2026-11-03** (section 8.3): Python oracle parity (7 search/replace, 5 single-hunk patches, 3 symbol sets, 5 pytest counts; firewall 14 agree + 11 explained divergences); 4 bad edits refused with every workspace file byte-identical; `git apply` of the module's own patches reproduces accepted bytes (CRLF, BOM, no-final-newline); tree kill verified by grandchild PID on Windows (Job Object) and Linux (process group); 12 real tool logs match hand-written expectations; the design-doc recipe validates against the built-in registry. **R20: not smaller (2815 C++ vs 1409 Python lines).** 1278 like-for-like lines (Workspace, Canvas, firewall, Execution) replace 1409 Python (-9%); the other 1537 replace Python stdlib (`subprocess` 561, `difflib` 248) or are capabilities Python lacked (syntax validation 204, diagnostics 283, module/schema validation 241) |
| M4 | `AgentLoop` + `ContextCondenser` (3 segments, R6) + **OrchestratorModule** + `RuntimeTierConfig` (R16) + one code recipe cartridge with a `post_llm_validation_hook` + a **run record** for the session fields that are not LLM memory (`task_id`, `mode`, `instance_id`, `step_index`, `ground_truth`, last interaction; section 8.1, D12) | Harness scenario `code_smoke_file` passes 3/3 on C++ (Python baseline 3/3 [doc]); the loop refuses to exit while the hook fails (forced-failure test). **Done 2026-11-04** (section 8.4): 138 unit test cases incl. all 21 correctness properties as RapidCheck tests over `ReplayBackend`; Python oracle parity for the token estimate and tail-keep; live `code_smoke_file` 3/3 and the forced-failure run ending at the turn limit with a non-success terminal; all five build lanes + the three CI jobs green at commit `d4bf9e5`. **R20: essentially flat (862 C++ vs 854 Python lines, +0.9%).** The condenser (175 vs 255), RuntimeTierConfig (59 vs 134) and RunRecord (54 vs 142) are smaller, and the loop deletes the 69-line heal/alias layer (H9); that saving is offset by capabilities Python lacked (a deterministic `must_succeed` exit gate, ring-buffer + spill, pre-wipe field validation, typed turn/run records) |
| M5 | `LlamaCppBackend` (upstream): KV checkpoint/rollback (`llama_memory_seq_rm`), GBNF for the R14 action call | Post-wipe prefill token count measured < full prompt; invalid JSON impossible in N trials |
| M6 | **KnowledgeModule** (SQLite + vector + embeddings + page cache) | Reads existing `fact_graph.db`; recall@k on fixture matches Python within tolerance |
| M7 | DocumentModule, PersonaModule, LearnModule (5.2) + recipe cartridges for research / writing / learn / persona; `ScriptModule` over `manifest.json` plugins (D5); `register_new_recipe`, nesting, `llm_micro_pass` (D9) | Capability parity scenarios re-expressed as cartridge tests; a sample plugin manifest loads and runs via stdin/stdout |
| M8 | CLI surface + **Qt 6 Widgets GUI shell** (D3): all current pages ported (G1-G12 in `GUI_EVALUATION.md`) | Each row G1-G12 has a passing check (manual QA list from Python `docs/workspace-qa-*.md` re-run on C++) |
| M9 | **Live canvas** for code + writing (D10, F1) + **GUI recipe builder** on QtNodes (D8, F2) | Highlight → agent edit → inline pending patch → accept/undo, scripted UI test; builder round-trips cartridge JSON losslessly |
| M10 | Remote server (52-route HTTP/WS contract, `webapp/` unchanged), MCP client + host, setup wizard, packaging (D6) | Existing `webapp/` works against the C++ server; MCP host tools listed by a client |

### 8.1 Core value types (M1)

Headers in `src/core/include/aquila/types/`. JSON is `nlohmann::ordered_json` (key order preserved). Canonical form: `dump(2)`, UTF-8 unescaped, trailing `\n`, keys in field order. Parsing is strict: unknown keys, duplicate keys, wrong types, and bad enum values throw `aquila::SchemaError` with a JSON Pointer path.

| Type | Fields (canonical order) | Python counterpart | Verdict (R19) |
|---|---|---|---|
| `Message` | `role` (system/user/assistant/tool), `content`, `images` (omitted if empty) | Ollama native shape from `adapt_messages_openai_to_native` (`parser/ollama_messages.py`) | **Same.** Byte-identical to Python output |
| `ChecklistItem` | `id`, `text`, `status` (pending/done/skipped) | `ChecklistItemState` (`core/run_state.py:64-79`) | **Same.** Byte-identical to Python output |
| `ActionResult` | `success`, `error_code`, `llm_facing_output`, `token_estimate` (u64) | `CapabilityResult{ok, data, summary, error_code, error_message}` (`capabilities/base.py:43-63`) | **Merged.** Keeps Python's `error_code` (all 32 codes at `759212a` accepted); `error_code` is empty exactly when `success`, so the loop never string-matches output (Python does: `"OS BLOCK" in summary` at `run_state.py:292`, `startswith("❌")` in 5 places). Drops `summary`/`error_message` (`failure()` sets both to the same text, `base.py:58-63`) and the `data` grab-bag that `format_capability_result_for_llm` re-parses into text (`base.py:66-97`); the module writes `llm_facing_output` once |
| `ActionCall` | `thought`, `module`, `action`, `args` (object) | Two turn formats: `{reasoning, tools[], final_report}` and `{reasoning, capabilities[]}` | **New.** One grammar-enforced format (R14). Python's `tools[]` is a list but only `tools[0]` runs (`core/code_agent.py:342`), and a heal layer repairs model drift (`code_agent.py:75-113`, H9). Completion becomes `OrchestratorModule.complete_recipe` instead of a separate `final_report` |
| `ToolInteraction` | `id`, `module`, `action`, `args`, `result` (ActionResult) | None: output is appended as a user message `"Tool Outputs:\n…"` (`code_agent.py:388`) | **New.** Python loses which action/args produced a result, so the tail can't be evicted or rendered per interaction. `tool_name` (D:L94-100) → `module` + `action` [interpretation] |
| `AgentScratchpad` | `active_objective`, `current_hypothesis`, `verified_facts`, `failed_approaches_do_not_repeat`, `next_immediate_action`, `checklist` | `TaskRunContext` (`core/run_state.py:95-220`) | **New** for the LLM's memory (R7; user, 2026-11-03). Python's free-text `run_digest` grows until an LLM pass compresses it (`run_state.py:82-92`), and `milestones` duplicates `checklist`. Session fields (`task_id`, `mode`, `instance_id`, `step_index`, `ground_truth`, `last_capability`) are not memory; they go to the M4 run record. Python's loader swallows errors and silently re-bootstraps (`run_state.py:165-170`); C++ rejects. `run_state.json` is not imported (D12) |
| `ActionSchema` | `action_name`, `description`, `parameters_json_schema` (object) | `CapabilitySpec.input_model` (Pydantic, `capabilities/registry.py:13-21`) | **New.** Plain JSON Schema, which feeds GBNF generation directly (M5) |
| `RecipeCartridge` | `recipe_id` (non-empty), `goal_template`, `load_modules` (≥1 of `module`, `initial_state`, `expose_actions`), `pre_llm_hooks` (`module`, `action`, `args`), `scratchpad_checklist`, `post_llm_validation_hook`? (`module`, `action`, `must_succeed`, `on_failure_instruction`) | `RECIPE_REGISTRY` (recipe id → capability ids, `functions/recipes.py`); scoping spread over `tool_catalog.py` / `step_policies.py` / `capabilities/adapters.py` | **New** (R12, D:L433-477). One cartridge holds modules, exposed actions, hooks, and the exit gate. Hook modules must be in `load_modules`; hook arrays may be omitted on input; D9 fields (`include`, `llm_micro_pass`) are rejected until M7. Real test: re-expressing Python's 15 recipes at M7 |

Re-verify: `python tests/fixtures/python/gen_python_fixtures.py` (needs the pinned Python checkout; regenerates `tests/fixtures/python/*.python.json` and `codes/error_codes.json`, which must leave `git status` clean), then any workflow preset. The unit test prints `golden: checked 17 fixtures (6 generated by Python)`, `error codes: 32 Python codes accepted`, the design-doc block line ranges, and the mutation counts.

### 8.2 Inference backend (M2)

`src/core/include/aquila/inference/`: `IInferenceBackend` (`append(Message)`, `mark_checkpoint`, `rollback_to`, `generate(params, on_token)`, `active_profile`, `supports_kv_reuse`), `OllamaHttpBackend`, and the pure wire functions in `ollama_wire.hpp`. Verdicts against Python's `OllamaClient` (`agent/core/main.py:273-1430`):

| Feature | Python | C++ | Verdict (R19/R20) |
|---|---|---|---|
| Temperature | Top-level `temperature` (`main.py:808`), ignored by Ollama | `options.temperature` | **Fixed** (H15) |
| Payload shape | `model, messages, temperature, stream, keep_alive?, options, format?, think?` | Same minus top-level temperature; `options` always present | **Same** otherwise; 7 Python cases match byte-for-byte after the fix |
| Interface | Messages in, dict out | Message-based context + checkpoints; the doc's `append_to_kv_cache(string_view)` (D:L640) is replaced because text loses role boundaries (no `/api/chat`, no chat template) | **New** |
| Output constraint | `format` dict, `"json_object"`→`"json"` (`main.py:781-789`) | `OutputConstraint{none, json, json_schema}`; GBNF is M5's translation | **Same** mapping, typed |
| Options source | 11 `AQUILA_*` env vars read at call time + a "surface" (chat/act/plan) | Explicit `GenerationParams`; only `OLLAMA_BASE_URL/MODEL/NUM_CTX/KEEP_ALIVE` via `OllamaConfig::from_env()` | **New**; surface→params policy moves to `RuntimeTierConfig` (M4) |
| Errors | Returned as model content, e.g. `"*(API Error: ...)*"` (`main.py:1152-1160, 1326, 1346, 1426-1430`) | `GenerationResult{ok, error_code, error_detail, ...}`; codes `unreachable, timeout, stream_stalled, stream_truncated, http_error, server_error, bad_response, cancelled, unsupported_url, invalid_request, transport_error` | **New** (callers can't confuse errors with output) |
| Fallbacks | Silent strict schema → json → plain degrade, plus a think-off retry (`main.py:1184-1424`) | One attempt, typed error | **New**; any fallback becomes explicit M4 policy |
| Connection | Probes Ollama at import (`client = OllamaClient()`, `main.py:1433`, H4) | No I/O until `probe()` or `generate()` | **New** |
| Streaming | Token generator + stall kill switch + stop check (`main.py:971-1150`) | Token callback (return `false` = `cancelled`), stall timeout → `stream_stalled`, missing `done` → `stream_truncated` | **Same** behavior, typed outcomes |
| Repetition guard, inline `<think>` strip/split | `main.py:990-997, 1120-1136` | Not ported | **Deferred** to M8 (GUI chat is the caller) |
| Thinking-only backfill | `main.py:1277-1280` (turboquant workaround) | Not ported | **Dropped** unless the stock server shows empty `content`; live tests on 0.40.14 returned content in all cases |
| Warmup, cold-start padding, model list/eject, kill wallclock mode | `main.py:309-731`, `986` | Not ported | **Deferred** to M8/M10 (model management); wallclock mode dropped |
| TLS | `requests` supports `https://` | `unsupported_url` (cpp-httplib built without OpenSSL) | **Gap**, recorded |

R20: 457 C++ lines (`inference/`) vs 644 Python lines in `main.py:732-1430`; part of the Python is deferred (above), not condensed. `main.py:273-731` (413 lines, model management) is not ported yet.

Re-verify: the generator (8.1) also writes `tests/fixtures/python/payloads/*.json` from the real `OllamaClient` (pinned tree required, client pinned to a closed port). The unit test prints `payload parity: 7 Python cases; only /temperature -> /options/temperature differs` and `stream_stalled after ~1.0s`. Live tests: section 1 "Building".

### 8.3 Modules, CanvasBuffer, workspace and execution (M3)

`IAgentModule` (doc interface + `configure(initial_state)`), `ModuleBase` (validates args against each action's JSON schema: `invalid_args` / `unknown_action`), `ModuleRegistry` (Option A, `builtin()` = Workspace + Execution, `validate_recipe` with recipe paths), `CanvasBuffer`, `PathFirewall`, `SyntaxService` (tree-sitter C/C++/Python), `exec::run`, `exec::diagnose`. Verdicts against Python (`agent/`):

| Area | Python | C++ | Verdict (R19) |
|---|---|---|---|
| Buffer state | JSON file rewritten on every call (`tool_library/code_canvas_tools.py:73-95`); dirty buffer vs. stale disk, so `run_pytest` auto-syncs (`:879`) | In RAM; accepted edits are written through atomically (temp + rename); state survives wipes via snapshots | **New** (no dirty state, no sync step) |
| Edit validation | None; `write_file` keeps broken code and reports success (`tool_library/code_agent_tools.py:124-133`) | tree-sitter parse before every edit; an edit that **adds** syntax errors or conflict markers is refused and nothing changes | **New** (the doc's guardrail, D:L362) |
| Pending patches | Full snapshots by list index; last accepted wins; `hash()`-based check never used (`code_canvas_tools.py:125-175`) | Stable ids, `base_version`; `stale_patch`, `disk_changed` (external edits are never overwritten) | **New** |
| Diffs | `difflib` with `lineterm=""` runs headers together | Myers line diff; checked by `git apply` (outside oracle) | **Fixed** |
| Line endings / encoding | `write_text` turns `\n` into CRLF on Windows; no encoding check | Per-file EOL and BOM preserved; non-UTF-8 refused (`unsupported_encoding`) | **Fixed** |
| `search_replace` semantics | Unique exact match; 0 / many / empty are errors | `surgical_edit`: same rules (7 oracle cases equal) | **Same** |
| Patch application | Single hunk correct; multi-hunk drifts (no offset) | `diff::apply` with hunk offsets (5 oracle cases equal) | **Same** where Python is right, **fixed** otherwise |
| Symbols | Python only, `ast.walk`, first 12 names | tree-sitter for C, C++, Python with line ranges (Python name sets equal `ast.walk`) | **Extended** |
| Path firewall | Name blocklist only, no containment; `.env` → `<root>/env`, `../x` → `x`, absolute paths outside the root readable (`core/tools.py:89-191`) | Canonical containment after resolving symlinks/junctions; drive-relative, device and outside-root UNC paths refused; secrets and `.git` always blocked; generated dirs write-blocked | **Fixed** (14 verdicts agree with Python; 11 divergences listed in `python_oracle_test.cpp`) |
| Commands | Prefix allowlist on the string, broken metacharacter check, timeout kills only the child, first 12k chars (`tool_library/run_tools.py:13-94`) | argv only (no shell), program allowlist + recipe build/test programs, cwd confined, secret env vars stripped, Job Object / process-group tree kill (also for orphans), head+tail capture; `.cmd`/`.bat` refuse cmd metacharacters (BatBadBut) | **Fixed** |
| Build/test output | Raw truncation; pytest counts by regex (`coding/language_registry.py:192-214`) | Parsers for MSVC, clang/gcc, CMake, ninja, pytest, Python tracebacks; identical diagnostics folded with counts; top 5 rendered (e.g. 3876 → 442 bytes for clang template spam) | **New**; pytest counts equal Python's on 5 real runs |

Re-verify: `python tests/fixtures/python/gen_python_fixtures.py` also writes `tests/fixtures/python/workspace/*.json` and the pytest logs; `scripts\msvc-dev.cmd python tests/fixtures/logs/capture_logs.py` re-captures the compiler/CMake/ninja/traceback logs (expectations in `*.expected.json` are hand-written). The unit tests print `oracle ...`, `guardrail: ...`, `git apply oracle ...`, `tree kill: ...`, `orphan cleanup: ...` and one `diagnose ...` line per log.

### 8.4 Agent loop, condenser, orchestrator, tiers, run record (M4)

New headers under `src/core/include/aquila/agent/` (`runtime_tier.hpp`, `run_record.hpp`, `context_condenser.hpp`, `orchestrator_module.hpp`, `agent_loop.hpp`, `recipes.hpp`) and sources under `src/core/agent/` wire the M1 value types, the M2 backend, and the M3 modules into one single-threaded deterministic loop (R2). `RuntimeTierConfig` is the single source of thresholds (R16); `ContextCondenser` holds the three KV segments (R6); `OrchestratorModule` owns the scratchpad and the completion-gate intents (R11); `RunRecord` carries the session fields that are not LLM memory (D12); `AgentLoop` drives one grammar-enforced action per turn and runs the deterministic exit gate (R12, R14). Verdicts against the Python each replaces (pinned `759212a`):

| Feature | Python | C++ | Verdict (R19/R20) |
|---|---|---|---|
| Loop driver | `code_agent.run_tool_session` + `_parse_tool_turn`/`_execute_tool`/`_max_turns`/path-repeat guards (`core/code_agent.py:28-411`) | `AgentLoop::run` + turn cycle | **New / improved.** One grammar-enforced `{thought, module, action, args}` format (R14), so the ~69-line heal/alias layer (`_heal_tool_action`, `_normalize_tool_arguments`, `_CAP_TO_TOOL`, H9) is **deleted, not ported**. Classification branches only on `success`/`error_code`, never on `llm_facing_output` text (Python string-matches `startswith("❌")` / `"OS BLOCK"`). Completion is a module action, not a free `final_report` |
| Condenser | `context_manager.build_loop_messages` (prompt assembly + ad-hoc token-cap truncation), `on_step_advance` (LLM-summarize on step advance), `_keep_recent_turns`, `compress_step_transcript`, `merge_workspace_summary` (`policies/context_manager.py:16-324`) | `ContextCondenser`: pinned prefix + anchored block + rolling-K ring buffer, head+tail spill with a recoverable ref, structural `condense()` | **New / improved.** Python LLM-summarizes a free-text digest and clears history on step advance; C++ keeps a fixed-structure wipe (prefix kept, anchor refreshed, tail cleared) with no model call, plus a spill buffer Python never had. 175 C++ vs 255 Python |
| RuntimeTierConfig | `context_budget.ContextProfile` tier table + `_limits_for_tier`/`_conversation_policy_for_tier`/`resolve_context_profile` keyed on `num_ctx` (`policies/context_budget.py:11-170`) | `RuntimeTierConfig`/`TierLimits`/`UniversalFlags` keyed on `ComputeProfile`, CPU-first default (GPU is an explicit boost) | **Improved, smaller.** Python keys tiers on context-window size; the doc keys on hardware and is CPU-first (R16). Universal flags (KV rollback, GBNF, n-gram) are present on every tier and report `false` on the Ollama scaffold so M5 flips them without a config change. 59 C++ vs 134 Python |
| OrchestratorModule | run-state bookkeeping + wipe triggered by the planner/loop, no field validation (`core/run_state.py`, `policies/context_manager.py:on_step_advance`) | `checkpoint_notes` / `trigger_context_condense` / `complete_recipe`, each validating required scratchpad fields before a wipe | **New.** Python never validates required scratchpad fields before compressing (R11); the module returns `missing_required_field` and leaves state unchanged on failure, and only requests a condense after validation passes |
| RunRecord | `TaskRunContext` session fields (`task_id`, `mode`, `instance_id`, `step_index`, `ground_truth`, `last_capability`) + `bootstrap`/`load`/`from_dict`/`to_dict`/`persist` (`core/run_state.py:37-226`) | `RunRecord{task_id, mode, instance_id, step_index, ground_truth, last_interaction}`, canonical JSON, strict parse | **New, smaller.** A separate value type for session state, distinct from `AgentScratchpad` (D12). `run_state.json` is **not imported** (fresh start); Python's loader swallows errors and silently re-bootstraps, C++ rejects with a JSON-pointer path. 54 C++ vs 142 Python. The digest/checklist/ground-truth *machinery* in `run_state.py` (render, compress, checkpoint) is not RunRecord's job; it maps to OrchestratorModule + the condenser |
| Exit gate | TDD soft gates in the loop; `harness_gate.py` is offline only; code mode can exit on a free `final_report` (`core/code_agent.py:356-360`) | `post_llm_validation_hook{must_succeed, on_failure_instruction}` run as a deterministic `HookCall` through the registry (no LLM turn); the loop cannot exit while it fails | **New.** The gate is a loop invariant, not advice. A `HookCall` may run an action absent from `expose_actions`; an LLM dispatch of the same action is rejected with `action_not_exposed`. A permanently failing gate ends `{outcome==turn_limit, success==false}` (Property 21) |

R20: the five components add **862 C++ src lines** [measured] (AgentLoop 327, ContextCondenser 175, OrchestratorModule 180, RuntimeTierConfig 59, RunRecord 54, plus `recipes.hpp` 60 and +7 in `modules/registry.cpp`/`builtin.cpp`) versus **854 Python lines** [measured] they replace (loop 323, condenser 255, tiers 134, run-record session portion 142; same non-blank / non-comment rule, pinned `759212a`). Net **essentially flat (+8 lines, +0.9%)** — not a clear win, and here is why: three components are smaller (RuntimeTierConfig 59 vs 134, RunRecord 54 vs 142, condenser 175 vs 255), and the loop deletes the 69-line heal/alias layer (H9) outright. That saving is offset by capabilities Python did not have — a deterministic `must_succeed` exit gate the loop cannot bypass, the rolling-K ring buffer with a recoverable spill, OrchestratorModule's pre-wipe field validation, and the typed `TurnRecord`/`RunRecord` transcript — so the C++ does strictly more in about the same number of lines. The `code_smoke_file.recipe.json` cartridge (48 lines) is a JSON resource, not counted in the C++ total (the `*.{cpp,hpp,cu}` glob excludes it).

Honest note for M5 (from the task 11.1 oracle): the C++ token estimate and Python's agree for ASCII but diverge for multi-byte text. `estimate_tokens` counts UTF-8 **bytes** and rounds up — `(text.size()+3)/4` (`src/core/modules/module.cpp:7-9`) — while Python's `estimate_messages_tokens` counts Unicode **code points** and rounds down — `len(content)//4` (`policies/context_manager.py:16-26`). For ASCII, bytes == code points and the two agree within rounding; for multi-byte content the C++ over-estimates by the continuation bytes. The oracle asserts the tight ASCII bound where it applies and the honest byte-derived bound otherwise (`python_oracle_test.cpp`); both are M4-acceptable but the estimator should move to a shared code-point (or real tokenizer) basis at M5.

Re-verify: all 21 correctness properties run as RapidCheck tests over `ReplayBackend` and a temp workspace (138 unit test cases total; 21 `[rapidcheck]`-tagged) — `tests/unit/agent_loop_test.cpp` (P1-P5, P15-P16, P19, synchronous-contract), `context_condenser_test.cpp` (P6-P10, P14), `orchestrator_module_test.cpp` (P11-P13, action set), `run_record_test.cpp` (P20, D12 field separation), `recipe_cartridge_test.cpp` (P17-P18, P21 forced-failure via the replay backend). Python parity for the condenser is `tests/unit/python_oracle_test.cpp` over `tests/fixtures/python/context/messages_estimate_*.json` and `keep_recent_*.json` (regenerate with `python tests/fixtures/python/gen_python_fixtures.py`; `git status` must stay clean). The network path is `tests/live/agent_loop_live_test.cpp`: `live: code_smoke_file passes the Python rubric 3/3` and `live: forced-failure reaches the turn limit with a non-success terminal` (excluded from CI; build with `-DAQUILA_LIVE_TESTS=ON` per section 1 "Building"). The C++ counts reproduce from the "How to re-verify" `rg` command (delta from the M3 baseline `src 3979`); the Python counts from the same non-blank/non-comment rule over the symbols named above at `759212a`.

---


### 8.5 LlamaCppBackend, context-strategy bake-off, and the M-RoPE finding (M5)

Per-feature verdict vs Python's `OllamaClient` and the R15 interface:

| Feature | Python | C++ (M5) | Verdict |
|---|---|---|---|
| Inference transport | Ollama HTTP per turn (`main.py`) | llama.cpp C API linked in-process (upstream b12116) | **New.** First real R15 direct backend; no HTTP per turn |
| KV checkpoint/rollback | n/a (Ollama resends full prompt) | `mark_checkpoint`/`rollback_to` -> `llama_memory_seq_rm` | **Real, with a model-class caveat (below)** |
| Structured output | `format` JSON mode + heal/alias (H9) | GBNF from `json_schema_to_grammar` + grammar sampler | **Improved.** Malformed JSON impossible by construction on the 9B (Proof 1: 54/54) |
| `UniversalFlags.kv_rollback` / `gbnf` | report false on the Ollama scaffold | flipped **true** for this backend | as M4 intended; no config-shape change |

**FINDING F1 (M-RoPE, GPU-proof).** Qwen 3.5 is recurrent/hybrid + M-RoPE. A mid-sequence
`llama_memory_seq_rm(mem,0,P,-1)` (0<P<end) does NOT rewind recurrent/positional state; the
next decode fails the inconsistent-position check (`X<Y` required) and the backend surfaces a
typed `decode_failed` (never a crash). Full reset (`rollback_to(0)`) is supported; mid-sequence
partial rollback is not. Proven in `tests/live/llama_backend_live_test.cpp`. This invalidated the
R6 KV-wipe condenser as the Qwen 3.5 context mechanism and triggered D14.

**FINDING F2 (4B GBNF degeneration).** The 4B Qwen3.5-Q4_K_M under the action-call GBNF opens a
valid object (`{ "thought":"`) then locks onto a zero-width token (vocab id 248319, empty
piece) and repeats it to the token cap -- tokens advance, no text. Diagnosed via per-token dump.
`generate()` now (a) lays down the assistant-turn opener before sampling (missing opener was why
smaller models emitted control/empty tokens) and (b) has a degenerate-output guard that stops
after 16 consecutive zero-width pieces with `error_code=degenerate_output`. The 9B does not hit
this; the 4B cannot complete a grammar-constrained action through this backend (open-model-under-
grammar risk, cf. NVIDIA arXiv:2611.05306 Appendix D). So the bake-off was decided on the 9B.

**D14 BAKE-OFF RESULT (Req 9) -- context-management strategy, decided by measurement, not argument.**
Three strategies behind the kept `ContextStrategy` interface (`src/core/context/`), scored over a
6-task multi-turn tool-use suite that plants a fact early and forces recall after an 8-turn detour
(`tests/live/bakeoff_tasks.hpp` + `context_bakeoff_live_test.cpp`), decision rule pre-committed
(accuracy > fewest tokens > lower latency; crash disqualifies). Run on Qwen3.5-9B-Q4_K_M, n_ctx 8192,
GPU (artifact `bakeoff-results/d14_bakeoff_9b_verdict.json`):

| Strategy | Completed | Crashed | Tokens | Secs |
|---|---|---|---|---|
| kv_rollback (control) | **1/6** | no | 1099 | 35.8 |
| eocc | **6/6** | no | 3059 | 39.2 |
| sac | **6/6** | no | 3089 | 42.9 |

**WINNER: EoCC** (End-of-Context Compaction) -- tied with SAC at 6/6, won on fewer tokens.
The *why* is decisive: kv_rollback's mid-sequence wipe corrupts the Qwen 3.5 context so the model
**fabricates** the planted facts (e.g. answers `config.json` for a file it was told was
`harness_report_7f3a.md`, `issue-123` for `AQ-20481`, `feature/fix-issue-123` for
`feature/bakeoff-metrics`) -- the KV approach is not merely unsupported, it is actively harmful on
this model. EoCC and SAC never do a mid-sequence wipe (full reset + rebuild), preserve every
planted fact, and complete 6/6. **D14 resolved: value-managed context (EoCC), not KV rollback.**
The winning `ContextStrategy` is M6's ContextCondenser starting point; `kv_rollback` stays behind
`UniversalFlags.kv_rollback` restricted to plain-RoPE / full-reset.

**R20 (M5).** Additive native backend (Python delegated inference to Ollama, so there is no Python
LOC to shrink here); the condensation it *enables* -- the parser/heal paths a grammar makes
unnecessary (H9) -- is credited when those are retired. Line counts recorded at commit time.


**FINDING F3 (model-family bake-off, 2026-11-05).** The D14 suite was re-run across model
families to answer whether the base model should change (the Qwen 3.5 M-RoPE + 4B-degeneration
problems are family-specific). Llama (plain-RoPE, arch `llama`) pinned from bartowski Q4_K_M:
Llama-3.2-3B-Instruct (CPU) and Meta-Llama-3.1-8B-Instruct (GPU), stored on D:.

| Model | Lane | kv_rollback | eocc | sac | GBNF actions |
|---|---|---|---|---|---|
| Qwen3.5-4B | CPU | - | - | - | **NO - zero-width degeneration (F2), 0/6** |
| Qwen3.5-9B | GPU | 1/6 | 6/6 | 6/6 | yes |
| Llama-3.2-3B | CPU | 1/6 | 6/6 | 6/6 | **yes (clean)** |
| Llama-3.1-8B | GPU | 1/6 | 6/6 | 6/6 | yes |

Conclusions:
- **CPU tier: Llama 3.2 3B >> Qwen 3.5 4B.** The 4B cannot produce a grammar-constrained action
  at all (F2); the 3B Llama completes 6/6 with EoCC/SAC. For a CPU-first agent (R16) this is a
  strong argument to make Llama the base family at the small size (proposed D15; R18 revisit).
- **D14 reconfirmed and generalized.** EoCC and SAC go 6/6 on every capable model; kv_rollback
  goes 1/6 on ALL of them -- including plain-RoPE Llama. So the KV-wipe approach is not merely
  unsupported on Qwen M-RoPE; it is the wrong mechanism for this recall pattern on every family
  (the mid-sequence wipe discards the tail that holds the planted fact). Value-managed context
  wins independent of model.
- SAC narrowly beats EoCC on both Llama models (fewer tokens, both 6/6); EoCC won on Qwen-9B.
  They are effectively tied; M6 can pick either as the ContextCondenser basis (SAC = fresh
  context per action; EoCC = grow-then-compact). GPU 8B ran the whole matrix in ~10s/strategy.

Artifacts: `bakeoff-results/d14_llama3b_cpu_verdict.json`, `d14_llama8b_gpu_verdict.json`,
`d14_bakeoff_9b_verdict.json`. Llama GGUFs pinned by SHA256 (bartowski):
Llama-3.2-3B-Instruct-Q4_K_M `6c1a2b41...728ff`; Meta-Llama-3.1-8B-Instruct-Q4_K_M `7b064f58...557c`.

## 9. Open decisions (need the user)

Decided (2026-11-02, by user):

- **D1 Branch model: DECIDED.** Python changes committed and pushed on `Aquila-3.5` (`759212a`). `Aquila-cpp` is an **orphan** branch in a separate worktree (`F:\Users\myfri\Aquila-cpp`).
- **D2 Inference: DECIDED.** Ollama over HTTP first (M2-M4, parity), then direct llama.cpp with KV control (M5).
- **D14 Context management: DECIDED by bake-off (section 8.5).** Value-managed EoCC, not mid-sequence KV rollback (Qwen 3.5 M-RoPE makes the wipe corrupt context). KV rollback kept behind a flag for plain-RoPE only.
- **D15 Base model family: DECIDED (user, 2026-11-05), evidence in section 8.5 F3.** Base pair = Llama 3.2 3B (CPU) + Llama 3.1 8B (GPU), plain-RoPE, pinned by SHA256 in cmake. R18 updated. Qwen 3.5 4B rejected (cannot do GBNF actions, F2); Qwen 3.5 9B kept as an alternate GPU option.
- **D4 llama.cpp source: DECIDED.** Upstream `ggml-org/llama.cpp`. Open follow-up: check whether the local fork's uncommitted Qwen 3.5 edits (section 1) are needed upstream.

- **D5 Extensibility: DECIDED.** `manifest.json` plugin scripts (reframed as script modules, section 2.2). MCP client/host is still rebuilt as an *integration surface* under D6; it's not the plugin mechanism.
- **D6 Scope: DECIDED.** Remake **everything** except Data Processing mode (to be rethought). That also drops `agent/vision/` (only used by data processing). In scope: all modes, GUI, Remote Companion, MCP, setup wizard, packaging, memory/sleep cycle, instances.
- **D7 Push: DONE.** `Aquila-cpp` pushed; remote == local `9cc8367` at push time.
- **D8 Recipe authoring: DECIDED.** GUI builder (QtNodes, M9). The Architect Agent stays a later idea.
- **D9 Primitives-era leftovers: DECIDED.** Keep `register_new_recipe`, recipe nesting, `llm_micro_pass`, all reframed for cartridges (section 2.2).
- **D10 Edit model: DECIDED.** Canvas buffer model. Aquila keeps and expands the canvas into a Gemini-style live canvas for code *and* writing. The move away from Canvas was for Lacerta (section 4 note).

- **D3 GUI: DECIDED.** **Qt 6 Widgets in C++** (evaluation: `GUI_EVALUATION.md`). It covers all 12 current capability rows plus canvas/builder/low-RAM, ports class-for-class, and drops `qfluentwidgets` for the built-in `windows11` style.
- **D11 Modules: DECIDED.** `CanvasBuffer` core + 7 modules: Workspace, Execution, Knowledge, Orchestrator, Document, Persona, Learn (section 5.2).
- **D12 Python run state: DECIDED (2026-11-03).** Per-task `run_state.json` (`TaskRunContext`) is **not imported**: it holds in-progress task state, not long-lived user data, so C++ runs start fresh. Long-lived data (H11: facts DB, vectors, ledgers) is still in scope.
- **D13 Error codes: DECIDED (2026-11-03).** `ActionResult.error_code` is a snake_case string (not a closed enum), so Python's 32 codes carry over and modules can add their own.

No decisions are open right now.

---

## Change log

| Date | Change |
|---|---|
| 2026-11-02 | Initial recon from `Aquila-3.5@0e51872` + dirty tree; PDF requirements R1-R17; hazards H1-H13; decisions D1-D6 |
| 2026-11-02 | Added H14 (partial test baseline; suite deferred per user) |
| 2026-11-02 | Pinned Python reference at `759212a` (H1 resolved); created orphan `Aquila-cpp` worktree; moved recon to `docs/recon/`; recorded D1/D2/D4; added local llama.cpp patch note and D7 |
| 2026-11-02 | Re-read design doc (now `docs/design/aquila-cpp-design.md`). Section 2 split into governing R1-R18 vs superseded S1-S7 (primitives → coarse modules, primitive-piping recipes → cartridges, 1-3 threads → single-threaded). Crosswalk, dispositions, and milestones re-aligned to modules. Added 5.1 module source map and D8-D11 |
| 2026-11-02 | D3 decided (Qt 6 Widgets C++), D11 decided (7 modules + CanvasBuffer core); no open decisions |
| 2026-11-02 | User answers: D5/D6/D8/D9/D10 decided, D7 pushed. Added `GUI_EVALUATION.md` (D3 recommendation: Qt 6 Widgets C++), section 5.2 module proposals (D11), Lacerta scope note, M8-M10 for GUI/canvas/builder/remote/MCP; vision + data processing out |
| 2026-11-02 | M0 build foundation. Section 1: toolchain facts (no clang-cl, no Windows LSan), Qt 6.11.3 install, deps table, build lanes. M0 proof row corrected (leak check moved to LSan on Linux + MSVC CRT debug heap) |
| 2026-11-03 | M1 core value types (section 8.1). Also fixed an M0 regression: `* text=auto` made fresh Windows clones check the design doc out as CRLF (sha256 `c6be44af…` instead of `5df25a18…`); the doc is now `-text` in `.gitattributes` |
| 2026-11-03 | Added rebuild goals R19 (improve; diverge from Python only with recorded evidence) and R20 (condense; LOC measured per milestone). Section 8.1 rewritten with a Python-counterpart verdict per type, and de-duplicated (the previous commit had inserted it twice). `ActionResult` gains `error_code` (D13); D12 (no `run_state.json` import); M4 gains the run record |
| 2026-11-03 | M2 inference backend (section 8.2). Added H15 (Python's temperature never applied) and H16 (Ollama app bugs); section 1 records the stock Ollama 0.40.14 setup and the `aquila:latest` Modelfile |
| 2026-11-03 | M3 modules and workspace (section 8.3); tree-sitter added to the deps table. R20 recorded honestly: M3 C++ is larger than the Python it replaces (reasons in the M3 row) |
| 2026-11-04 | M4 agent loop, condenser, orchestrator, tiers, run record (section 8.4). 21 correctness properties as RapidCheck tests, Python oracle parity, live 3/3 + forced-failure; all five lanes + CI green at `d4bf9e5`. R20 recorded: M4 is essentially flat (862 C++ vs 854 Python, +0.9%) — condenser/tiers/run-record smaller and the heal/alias layer deleted, offset by capabilities Python lacked. Added the token-estimate byte-vs-code-point divergence as an honest M5 note; after-M4 C++ size line (`src 4841, tests 4451`) |
| 2026-11-05 | M5 LlamaCppBackend + context-strategy bake-off (section 8.5). Direct llama.cpp (upstream b12116), GBNF action calls (9B Proof 1: 54/54 valid). FINDING F1: Qwen 3.5 M-RoPE cannot do mid-sequence KV rollback (typed decode_failed, not a crash). FINDING F2: 4B degenerates on GBNF (zero-width-token loop; assistant-opener + degenerate-output guard added). D14 decided by bake-off on the 9B: EoCC wins 6/6 (SAC 6/6, kv_rollback 1/6 -- the KV wipe fabricates planted facts). Value-managed context seeds M6; kv_rollback gated to plain-RoPE |
| 2026-11-05 | Model-family bake-off (section 8.5 F3): Llama 3.2 3B (CPU) + Llama 3.1 8B (GPU), bartowski Q4_K_M, pinned by SHA256, stored on D:. Qwen 3.5 4B cannot do GBNF actions (0/6, degenerates); Llama 3.2 3B does (6/6). D14 reconfirmed across families (kv_rollback 1/6 everywhere incl. plain-RoPE). **D15 DECIDED: Llama base pair; R18 updated**; Qwen 3.5 9B kept as alternate GPU option |
