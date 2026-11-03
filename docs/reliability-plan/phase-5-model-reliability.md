# Phase 5: Model Reliability

**Status:** Not started (ongoing)  
**Estimate:** Ongoing — parallel with Phases 1–4  
**Depends on:** [Phase 0](phase-0-baseline-and-gates.md)  
**Blocks:** Long-term competitiveness

## Goal

Close the largest reliability gap — local model tool-calling quality — without cloud dependency. Harness and evals drive model promotion.

## Problem

Enterprise agents assume ~90%+ correct tool selection on first try. Aquila compensates with:
- `heal_calls.py` (infer cap ID from arg shape)
- Flat Ollama JSON schemas (no per-arg validation in format)
- Coaches and OS BLOCK repetition messages

These are band-aids. Reliability requires model quality + simple schemas + measurement.

## Deliverables

### 5.1 — Tool-call evaluation set

- [ ] New directory: `agent/evals/`
- [ ] `agent/evals/code_tool_calls.jsonl` — held-out examples:
  ```json
  {"messages": [...], "expected_tool": "search_replace", "expected_args_subset": {"path": "habit.py"}}
  ```
- [ ] Scenarios cover: read, write, search_replace, grep, run_command, error recovery
- [ ] `agent/evals/run_tool_call_eval.py` CLI:
  ```bash
  python -m agent.evals.run_tool_call_eval --model aquila:latest
  ```
- [ ] Metrics: `parse_rate`, `correct_tool_rate`, `args_field_accuracy`, `wall_s`

### 5.2 — Capability-call evaluation set (research)

- [ ] `agent/evals/research_capability_calls.jsonl`
- [ ] Reuse research parity test fixtures where possible
- [ ] Same CLI, different schema kind

### 5.3 — Eval gates in model promotion

- [ ] Document promotion workflow in `docs/ollama-qwopus.md` or new `docs/model-promotion.md`
- [ ] New model tag promoted to `aquila:latest` only if:
  - [ ] Tool-call eval ≥ 95% correct_tool_rate
  - [ ] Harness `code_habit_tracker` 3/3 pass
  - [ ] Harness research smoke pass
- [ ] `model_tiers.py` updated with new verified tags

### 5.4 — Fine-tune data pipeline (local)

- [ ] `agent/evals/export_sft_pairs.py`
  - Export harness failures + eval misses as instruction/response pairs
  - Format matches Aquila tool-call JSON contract
- [ ] Document fine-tune workflow (external to repo or `ml-lab-vision.md` link)
- [ ] **No cloud training required** — user runs locally

### 5.5 — Schema simplification audit

- [ ] Code tool schema: minimal fields (`tool`, `arguments`, `reasoning`)
- [ ] Remove nested capability ID patterns that trigger `heal_calls`
- [ ] Document in [structured-output.md](../structured-output.md)
- [ ] A/B: flat vs enriched schema on eval set

### 5.6 — Thinking policy for code

- [ ] Code mode: always `force_think_disabled=True` (already in `code_chat`)
- [ ] Confirm no thinking tier injection in `code_agent` path
- [ ] Thinking tiers remain for research synthesis only

### 5.7 — Model fallback (opt-in cloud)

- [ ] **Optional** — only if user explicitly wants:
  - Env: `AQUILA_CODE_FALLBACK_API=openai|anthropic|none`
  - Trigger: 3 consecutive parse failures in one session
  - User consent dialog in GUI
- [ ] Default: `none` (local only)
- [ ] Log when fallback used; never silent

### 5.8 — Continuous regression

- [ ] Weekly harness matrix script (extend `scripts/aquila-capability-run.sh`)
- [ ] Compare reports week-over-week in `Agent-Logs/capability-runs/`
- [ ] Alert on turn count or wall time regression >20%

### 5.9 — Tests

- [ ] `agent/tests/test_tool_call_eval.py` — eval runner on fixture model mock
- [ ] `agent/tests/test_model_tiers.py` — extended for promotion list

## Files to touch

| File | Change |
|------|--------|
| `agent/evals/code_tool_calls.jsonl` | **New** |
| `agent/evals/research_capability_calls.jsonl` | **New** |
| `agent/evals/run_tool_call_eval.py` | **New** |
| `agent/evals/export_sft_pairs.py` | **New** |
| `agent/policies/model_tiers.py` | Promotion gates |
| `docs/model-promotion.md` | **New** |
| `docs/structured-output.md` | Schema simplification notes |

## Exit criteria

- [ ] Eval set ≥ 50 code tool-call examples
- [ ] `aquila:latest` scores ≥ 95% `correct_tool_rate` on held-out eval
- [ ] Documented promotion workflow used at least once
- [ ] `heal_calls` invocation rate < 5% of code turns (measured via session JSONL)
- [ ] qwopus either passes gate or is permanently in `CODE_DEGRADED_MODELS`

## Metrics dashboard (minimal)

| Metric | Source | Target |
|--------|--------|--------|
| `correct_tool_rate` | eval CLI | ≥ 95% |
| `parse_failures / turn` | session JSONL | < 0.05 |
| `heal_invocations / turn` | session JSONL | < 0.05 |
| Habit tracker wall time | harness | < 45s |
| Eval set size | jsonl line count | ≥ 50 (code), ≥ 30 (research) |

## Risks & open questions

| Item | Notes |
|------|-------|
| Eval set staleness | Refresh when tool surface changes (Phase 1) |
| Fine-tune infra | May live outside this repo |
| qwopus investment | **Open:** fix weights vs deprecate |
| Cloud fallback scope | Privacy-sensitive users may reject entirely |
| Multi-model routing | Future: small model for read, large for edit |

## Out of scope

- Training new base models from scratch
- Hosted inference service
- Automatic cloud fallback without consent

## Parallel work

Phase 5 can start in **week 1** alongside Phase 0:
1. Build eval JSONL from known good harness transcripts
2. Run eval on current `aquila:latest` to establish baseline score
3. Use failures to prioritize fine-tune data

## Reference commands

```bash
# Baseline eval
python -m agent.evals.run_tool_call_eval --model aquila:latest --report Agent-Logs/eval-baseline.json

# Export failures for SFT
python -m agent.evals.export_sft_pairs --from Agent-Logs/code-sessions.jsonl --out agent/evals/sft_export.jsonl

# Full gate including eval
./scripts/harness_gate.sh && python -m agent.evals.run_tool_call_eval --min-correct-rate 0.95
```
