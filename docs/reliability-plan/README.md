# Aquila Reliability Plan

Bring Aquila's agent loop in line with enterprise coding-agent reliability **while keeping local/privacy-first execution** and doubling down on batched capabilities + harness QA.

## North star

> **One dumb loop, sharp tools, batched capabilities only where they earn their complexity — all gated by harness pass/fail.**

| Surface | Loop | Execution |
|---------|------|-----------|
| **Code** | Chat-like, no planner | 6–8 filesystem + shell **tools** |
| **Research / Writing / Learn** | Optional thin plan | **Capabilities** (batched recipes) |
| **Chat** | Stream, no tools | Memory + optional light web |

## What we keep (Aquila advantages)

- Local Ollama — no cloud required
- Capability registry + Pydantic validation (`agent/capabilities/`)
- Batched research/writing/learn pipelines (fewer LLM turns)
- Recursive harness + scorecards (`agent/core/capability_harness.py`)
- Chroma / local embeddings for memory and search

## What we change

- Code mode: capabilities + Code Canvas buffer → direct FS tools
- `LoopEngine` code FSM → deleted or frozen; one code path via tool loop
- Model gate: harness-verified models only for code
- Coaches/heal layers as primary strategy → harness + simpler schema

## Phases

| Phase | Doc | Est. | Depends on |
|-------|-----|------|------------|
| **0** | [Baseline & gates](phase-0-baseline-and-gates.md) | 1 week | — |
| **0.7** | (in Phase 0 doc) Gate honesty — items **A–E** bridge on `code_chat` | ~2 days | 0 |
| **1** | [Enterprise code tools](phase-1-enterprise-code-tools.md) | 2–3 weeks | 0, 0.7 |
| **2** | [Context layer](phase-2-context-layer.md) | 1–2 weeks | 1 |
| **3** | [Slim the OS](phase-3-slim-the-os.md) | 2 weeks | 1 (partial overlap with 2) |
| **4** | [Unified agent loop](phase-4-unified-agent-loop.md) | 2–3 weeks | 1, 3 |
| **5** | [Model reliability](phase-5-model-reliability.md) | Ongoing | 0 |
| **6** | [Aquila advantages](phase-6-aquila-advantages.md) | After 1–4 stable | 0, 4 |

Suggested order: **0 → 0.7 → 1 → 3 → 2 → 4 → 5 (parallel) → 6**.

### Live baseline learnings (A–E)

| Item | Phase | What |
|------|-------|------|
| **A** | 0.7 + 1 | Honest `evaluate_run` for code (session metrics / disk, not `finish_task` JSONL) |
| **B** | 0.7 + 1 | Contract tests that match live gate behavior |
| **C** | 0.7 bridge, 1 if needed | `args`→`arguments` heal; simpler tool schema in Phase 1 |
| **D** | 0.7 minimal, 1 full | Write size limits + repeat-path guards |
| **E** | 0.7 + 1 exit | Re-run `--baseline` after each phase |

Phases **2–6** do not cover A–E; Phase **5** adds model eval/promotion after the loop is honest.

## Success metrics (3-month targets)

| Metric | Baseline (Aug 2026) | Target |
|--------|---------------------|--------|
| Habit tracker harness (`aquila:latest`) | ~51s pass; qwopus 180s timeout | < 45s, 3/3 consecutive passes |
| Code parse failure rate | Unknown | < 5% per session |
| Lines in active code execution path | ~11k (`loop_engine` + `main` + policies) | < 1.5k |
| Turns for `code_smoke_file` | ~6 | ≤ 4 |
| Research capability parity tests | Passing | Still passing |
| Code mode plan review | Enabled (broken for code) | Disabled / removed |

## Architecture target

```
┌─────────────────────────────────────────────────────────┐
│  agent_loop.py (~300 lines)                             │
│  turn: model → parse → execute → append → repeat        │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ToolExecutor    CapabilityExecutor   Policies (minimal)
   (code)          (research/writing)
         │               │
         ▼               ▼
   Real FS + shell    Registry + recipes
```

## Related docs

- [code-mode.md](../code-mode.md) — current simple code mode (transitional)
- [capability-modules-vision.md](../capability-modules-vision.md) — capability design (keep for batch modes)
- [aquila-recursive-harness.md](../aquila-recursive-harness.md) — harness MCP + CLI
- [structured-output.md](../structured-output.md) — Ollama JSON schema constraints
- [lacerta-supervisor-worker-viability.md](../lacerta-supervisor-worker-viability.md) — Lacerta Supervisor–Worker architecture (incl. MCP/Remote late plan)
- [lacerta-port-kit.md](../lacerta-port-kit.md) — CodeWorker / IPC / harness contracts (phases L0–L12)
- [lacerta-surfaces-and-recipes.md](../lacerta-surfaces-and-recipes.md) — surfaces & recipes (code → learn → research → writing)

## Status

| Phase | Status | Notes |
|-------|--------|-------|
| 0 | Complete | Baseline, gates, model tiers, session metrics |
| 0.7 | Complete | Gate honesty A–E on `code_chat`; smoke **3/3** |
| 1 | Implemented | Tool loop shipped; smoke **3/3**, habit **0/3** (parse/model tuning) |
| 2 | Complete | Snapshot, find_files, optional semantic_search + auto-context; smoke **3/3** |
| 3 | Complete | LoopEngine frozen for code; harness/GUI/tests/docs cleaned; smoke re-run |
| 4 | Not started | |
| 5 | Not started | |
| 6 | Not started | |

_Update this table as phases progress._
