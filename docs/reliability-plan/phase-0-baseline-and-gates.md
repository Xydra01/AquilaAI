# Phase 0: Baseline & Gates

**Status:** Complete (§0.7 gate honesty shipped 2026-09-02)  
**Estimate:** 1 week  
**Depends on:** —  
**Blocks:** Phase 1, Phase 5

## Goal

Stop flying blind. Establish measurable baselines, harness CI gates, and model-tier policy before rewriting code execution.

## Problem

- Code reliability varies wildly by model (`aquila:latest` ~51s vs `aquila-qwopus-standard` 180s timeout on same scenario).
- No enforced gate before shipping code-mode changes.
- Metrics (parse failures, heal invocations, turn counts) are not tracked consistently.

## Deliverables

### 0.1 — Harness gate script

- [x] Create `scripts/harness_gate.sh` (or `scripts/harness_gate.py`)
- [x] Runs required scenarios and exits non-zero on failure:
  - `code_smoke_file`
  - `code_habit_tracker` (LLM authorship, not scaffold)
- [x] Optional: `--engine stock|tq`, `--model` override
- [x] Document in [aquila-recursive-harness.md](../aquila-recursive-harness.md)

```bash
./scripts/harness_gate.sh
# or
python -m agent.core.capability_harness code_habit_tracker --engine stock
```

### 0.2 — Align harness with `code_chat` path

- [x] Update `code_habit_tracker` scenario in `agent/core/capability_harness.py`:
  - Remove `force_micro_plan` / `slot_fill` assumptions where obsolete
  - Ensure `run_mode` → `run_code_session` (not full `LoopEngine` FSM)
- [x] Verify `code_smoke_file` hits same path
- [x] Save reports to `Agent-Logs/capability-runs/` with consistent schema

### 0.3 — Model tier registry

- [x] New file: `agent/policies/model_tiers.py`
  - `CODE_CAPABLE_MODELS` — harness-verified only
  - `CODE_DEGRADED_MODELS` — warn or block
  - `get_active_model_id()` helper
- [x] Code mode entry (`main.py` / `code_chat.py`): check tier before session start
  - Hard block or prominent GUI warning for degraded models
- [x] Log model ID in every harness report JSON

### 0.4 — Session metrics

- [x] Extend harness report + `code_chat` session with:
  - `turns`, `wall_s`, `parse_failures`, `capability_or_tool_errors`
  - `heal_invocations` (if heal layer runs)
  - `repeat_blocks` (if coach fires)
  - `model_id`, `engine`
- [x] Optional: append one JSONL line per code session to `Agent-Logs/code-sessions.jsonl`

### 0.5 — Baseline capture

- [x] Run harness 3× on `aquila:latest` and record results (2026-09-01 initial; **2026-09-02** after 0.7)
- [x] Run harness 3× on default `.env` model; record fail mode (same as capable model when `OLLAMA_MODEL=aquila:latest`)
- [x] Document required model in `.env.example` and [code-mode.md](../code-mode.md)

Use:

```bash
./scripts/harness_gate.sh --runs 3 --baseline
```

Results saved to `Agent-Logs/baseline-aug-2026.json` (2026-09-02 re-capture after 0.7, ~8 min wall).

| Model | Scenario | Pass rate | Avg wall_s | Avg turns | Notes |
|-------|----------|-----------|------------|-----------|-------|
| aquila:latest | code_smoke_file | **3/3** | 9 | 3 | Honest `evaluate_run`; synced + file on disk |
| aquila:latest | code_habit_tracker | 0/3 | 126 | 16 | Files not synced; deferred to Phase 1 |

**Gate overall:** `ok: false` — smoke green; habit tracker still fails acceptance (expected until Phase 1 tool loop).

### 0.6 — Tests

- [x] `agent/tests/test_model_tiers.py` — tier lookup, block/warn behavior
- [x] `agent/tests/test_harness_gate.py` — smoke test gate script (mock harness)
- [ ] CI hook (optional): pytest marker `@harness` for live Ollama runs (`conftest.py` registers marker; gate remains manual until CI has Ollama)

### 0.7 — Gate honesty close-out (live baseline learnings)

The 2026-09-01 baseline showed **smoke file succeeded** (`code_session_metrics.synced=true`, 3 turns) but the gate failed because the scorecard still expects LoopEngine `finish_task` / `tool_end` JSONL. Close this gap **before Phase 1** so the gate measures reality on the current `code_chat` path.

| ID | Deliverable | Owner phase |
|----|-------------|-------------|
| **A** | `evaluate_run` for `mode=code`: pass when `code_session_metrics.synced` is true **or** acceptance file checks pass; do not require scorecard `require_finish` / `tool_end` when `code_session` is present | **0.7** |
| **B** | Contract tests: report with `synced=true` + file on disk ⇒ `evaluate_run` passes even if `scorecard.finish_task` is false | **0.7** |
| **C** | `heal_calls`: normalize `args` → `arguments` on capability payloads (habit tracker live failure) | **0.7** (bridge); Phase 1 uses simpler tool schema |
| **D** | `create_file` max content + repeat guard on same path (2× block → coach / fail fast) in `code_chat` | **0.7** (minimal); full guards in Phase 1 `write_file` loop |
| **E** | Re-run `./scripts/harness_gate.sh --runs 3 --baseline` after 0.7; update baseline JSON + table below | **0.7** exit |

- [x] **A** — Update `evaluate_run` / `score_jsonl_for_scenario` code-mode branch in `capability_harness.py` / `capability_scorecard.py`
- [x] **B** — `agent/tests/test_code_eval_contract.py` (or extend `test_capability_harness.py`)
- [x] **C** — `heal_calls.py`: `args` → `arguments`; test in `test_heal_capability_calls.py`
- [x] **D** — `code_chat.py` or `create_file` cap: max content env (`AQUILA_CODE_MAX_CREATE_CHARS`); repeat-path counter
- [x] **E** — Baseline re-capture; smoke target **3/3** pass after A

**Not in Phase 0:** JSONL `tool_end` emission — deferred to Phase 1 `code_agent` loop (observability nice-to-have once tools land).

## Files to touch

| File | Change |
|------|--------|
| `scripts/harness_gate.sh` | **New** |
| `agent/policies/model_tiers.py` | **New** |
| `agent/core/capability_harness.py` | Scenario alignment, report fields |
| `agent/core/code_chat.py` | Metrics emission, model gate call |
| `agent/core/main.py` | Model gate on code mode entry |
| `docs/code-mode.md` | Model requirements, gate docs |
| `docs/aquila-recursive-harness.md` | Gate script reference |

## Exit criteria

- [x] **0.7 complete:** smoke file **3/3** on gate after honest evaluation (not scorecard theater)
- [ ] `code_habit_tracker` passes **3/3** on gated model — deferred to Phase 1; 0.7 only requires honest gate + smoke green
- [x] Gate script exits 0 on pass, non-zero on fail
- [x] Degraded model produces clear user-visible warning or block
- [x] Baseline JSON committed or documented with turn/time stats (`Agent-Logs/baseline-aug-2026.json`)
- [x] Baseline **re-captured** after 0.7 (item E)

## Target metrics (habit tracker)

| Metric | Target |
|--------|--------|
| Wall time | < 60s (stretch: < 45s) |
| Turns | < 12 |
| Parse failures | 0 |
| Synced files | `habit.py`, `tests/test_habit.py`, `README.md` |

## Risks & open questions

| Item | Notes |
|------|-------|
| Ollama not running in CI | Gate may be manual/local only initially |
| Which models in `CODE_CAPABLE_MODELS`? | Start with harness-passing only; expand via eval |
| Block vs warn for degraded models | **Resolved:** hard block in GUI; warn in CLI; strict harness unless `--allow-degraded` |
| Habit tracker flakiness | May need to fix prompt/model before gate is stable |

## Out of scope

- Rewriting code tools (Phase 1)
- Deleting `LoopEngine` (Phase 3)
- Fine-tuning models (Phase 5)
