# Aquila Recursive Capability Harness

Run **completable** Aquila scenarios per mode on **stock** (`:11434`) and **TurboQuant** (`:11435`), collect tokens/tools/time data, and **pass/fail before advancing** to the next scenario. Designed for Cursor + MCP iterative improvement.

See also: [aquila-mcp-host.md](aquila-mcp-host.md), [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md).

## MCP tools

| Tool | Purpose |
|------|---------|
| `aquila_list_scenarios` | List harness scenario IDs |
| `aquila_run_scenario` | Run one scenario (`engine`: `stock` / `tq`) |
| `aquila_evaluate_run` | Rubric + write `Agent-Logs/capability-runs/*.json` |
| `aquila_get_task_metrics` | Poll tokens/s while running |
| `aquila_probe_throughput` | Baseline before matrix (`engine=both`) |
| `aquila_release_generation_lock` | Clear stale/orphan locks |
| `aquila_health` | Ollama + lock status |

## Scenarios (local-first)

| ID | Mode | Acceptance |
|----|------|------------|
| `code_smoke_file` | code | `Agent-Code/harness-smoke/harness_smoke.py` prints `HARNESS_OK` |
| `code_local_read` | code | Local read + deliverable |
| `research_local_lock` | research | Local files, min 400 chars deliverable |
| `writing_short` | writing | Min 300 chars draft |
| `task_lock_check` | task | Min 200 chars on lock behavior |

Definitions live in [`agent/core/capability_harness.py`](../agent/core/capability_harness.py).

## Cursor loop (per scenario)

1. `aquila_health` and `aquila_probe_throughput(engine="both")`
2. `aquila_list_scenarios(mode="code")` (advance mode order: code → research → writing → task)
3. `aquila_run_scenario(scenario_id="...", engine="stock")` — save `task_name`
4. Poll `aquila_get_task_metrics` every 30–60s until idle
5. `aquila_evaluate_run(mode, task_name, scenario_id, engine)` — **do not advance if `passed` is false**
6. On failure: inspect `jsonl_path`, fix Aquila code, `aquila_release_generation_lock` if needed, re-run (max **2** attempts per scenario per engine)
7. Repeat for `engine="tq"`
8. Compare reports under `Agent-Logs/capability-runs/`

## CLI (no Cursor)

```bash
./scripts/aquila-capability-run.sh clear-lock
./scripts/aquila-capability-run.sh matrix --engine both
./scripts/aquila-capability-run.sh matrix --engine stock --scenario code_smoke_file
```

Env:

| Variable | Default | Meaning |
|----------|---------|---------|
| `AQUILA_HARNESS_MAX_WALL_S` | 600 | Whole-matrix timeout (Linux `timeout`) |
| `AQUILA_EXPECTED_TOKENS_PER_S` | 30 | Stock baseline |
| `AQUILA_TQ_EXPECTED_TOKENS_PER_S` | 30 | TQ baseline |

## Report schema

Written to `Agent-Logs/capability-runs/{scenario}_{engine}_{timestamp}.json` and indexed in `index.jsonl`:

- `wall_time_s`, `llm_turns`, `tool_calls`, `tool_starts`
- `median_output_tokens_per_s`, `total_output_tokens_est`
- `throughput_health`, `scorecard_failures`, `passed`
- `jsonl_path`, `deliverable_path`

## Safety

- Do not run long `python -c` research jobs without timeout in agent terminals (orphan GPU risk).
- Use `aquila_release_generation_lock` after aborted MCP runs.
- Only one generation at a time (`generation.lock`).

## Session baseline (2026-06-02)

| Check | Result |
|-------|--------|
| Unit tests | `aquila-capability-run.sh pytest` — harness + ledger + scorecard |
| Stock Ollama `:11434` | Reachable; probe ~4–15 tok/s (below 30 baseline → `slow`) |
| TurboQuant `:11435` | Not reachable this session — matrix records `skipped` per engine |
| `code_smoke_file` (stock) | **Pass** after sandbox objective (`init_code_project('harness-smoke')`), ~167s, tps ~10 (`slow`) |
| `code_smoke_file` (tq) | Skipped when `:11435` down |

**Loop fixes this session:** `run_logger` duplicate `ollama_base_url` kwarg (blocked `finish_task` / ledger complete); `_sync_ledger_after_run` safety net; harness `force_micro_plan` + `code_micro_single_step`; MCP `aquila_evaluate_run` loads deliverable from ledger/JSONL.

Re-run after fixes:

```bash
./scripts/aquila-capability-run.sh matrix --engine stock --scenario code_smoke_file
./scripts/aquila-capability-run.sh matrix --engine both   # when TQ is up
```

## Later

- `research_web` scenario with live SearXNG
- Parallel scenarios (blocked by single GPU lock today)
- `task_micro_delegate` / `persona_build_lore_local` harness scenarios
