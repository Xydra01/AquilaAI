# Phase 6: Aquila Advantages

**Status:** Not started  
**Estimate:** After Phases 1–4 stable (ongoing polish)  
**Depends on:** [Phase 0](phase-0-baseline-and-gates.md), [Phase 4](phase-4-unified-agent-loop.md)  
**Blocks:** —

## Goal

Once code mode is reliable, **invest where Aquila beats enterprise agents** — not where it chases them.

## Aquila's durable differentiators

| Advantage | Enterprise gap |
|-----------|----------------|
| 100% local / private | Cursor, Claude Code, Codex are cloud-first |
| Batched capabilities (research) | Raw tool orchestration burns turns |
| Explicit harness + scorecards | No user-visible QA infrastructure |
| Multi-mode agent (research, writing, learn, code) | Single-purpose coding agents |
| Instance profiles + Chroma memory | Per-user local memory |

Phase 6 expands and polishes these — **not** more code FSM layers.

## Deliverables

### 6.1 — Harness expansion

Add scenarios beyond habit tracker:

| Scenario ID | Mode | Acceptance |
|-------------|------|------------|
| `code_fix_failing_test` | code | Given broken test file, agent fixes impl, pytest green |
| `code_add_cli_flag` | code | Add `--json` flag to existing CLI |
| `code_refactor_rename` | code | Rename symbol across 2–3 files |
| `code_read_only_audit` | code | Summarize module, no edits |
| `research_multi_source` | research | ≥3 sources, min deliverable chars |
| `writing_technical_doc` | writing | Structured doc with sections |

- [ ] Add scenarios to `capability_harness.py`
- [ ] Rubrics in `capability_scorecard.py`
- [ ] Document in [aquila-recursive-harness.md](../aquila-recursive-harness.md)
- [ ] `harness_gate.sh` tiers:
  - **Smoke:** `code_smoke_file`, `research_local_lock`
  - **Standard:** + `code_habit_tracker`, `writing_short`
  - **Full:** all scenarios

### 6.2 — Harness GUI / reports

- [ ] GUI page or panel: last N harness runs (pass/fail, wall time, turns)
- [ ] Read from `Agent-Logs/capability-runs/*.json`
- [ ] "Run smoke gate" button for developers
- [ ] Optional: sparkline of habit tracker wall time over time

### 6.3 — Research recipe expansion

- [ ] More composers in `agent/functions/recipes.py`:
  - `fn.research.literature_review`
  - `fn.research.compare_sources`
  - `fn.research.fact_check`
- [ ] MCP tool docs: `aquila_run_research_capability` examples
- [ ] Reduce act turns for typical research task by 30% (measure via harness)

### 6.4 — Offline bundle

- [ ] Document one-command setup: Ollama + Aquila model + passing harness snapshot
- [ ] Extend [packaged-install.md](../packaged-install.md):
  - Bundled model tag that passes smoke gate
  - Post-install: run `./scripts/harness_gate.sh --smoke`
- [ ] Installer shows ✅ or ❌ harness result

### 6.5 — Code mode polish (not more OS)

- [ ] `apply_patch` tool if `search_replace` proves insufficient in harness
- [ ] `git_status` / `git_diff` tools (read-only) for local workflow
- [ ] Stream tool output in GUI like chat tokens
- [ ] Session history: resume code session from `Agent-Logs/code-sessions.jsonl`

### 6.6 — Writing / learn parity

- [ ] Writing uses `plan_runner` + capabilities (Phase 4)
- [ ] Learn syllabus build: harness scenario `learn_syllabus_smoke`
- [ ] Cross-mode: research → writing handoff recipe

### 6.7 — Privacy & trust features

- [ ] "Local only" badge in GUI when no cloud fallback configured
- [ ] Audit log: all file writes + commands with timestamps
- [ ] Export session transcript for user review (markdown)

### 6.8 — Documentation

- [ ] `docs/aquila-vs-cloud-agents.md` — honest positioning doc
- [ ] Update [roadmap-3.5.md](../roadmap-3.5.md) or create `roadmap-reliability.md` with Phase 6 items

## Files to touch

| File | Change |
|------|--------|
| `agent/core/capability_harness.py` | New scenarios |
| `agent/core/capability_scorecard.py` | New rubrics |
| `agent/functions/recipes.py` | Research composers |
| `scripts/harness_gate.sh` | Tier flags |
| `agent/gui/gui_pages/` | Harness report panel (new or settings) |
| `docs/packaged-install.md` | Post-install gate |
| `docs/aquila-vs-cloud-agents.md` | **New** |

## Exit criteria

- [ ] ≥ 10 harness scenarios with rubrics
- [ ] Smoke gate runs in < 5 minutes on gated hardware
- [ ] Packaged install docs include harness verification step
- [ ] Research `research_multi_source` passes on gated model
- [ ] User-facing "local only" indicator shipped

## Success metrics

| Metric | Target |
|--------|--------|
| Harness scenario count | ≥ 10 |
| Research act turns (local_lock scenario) | −30% vs Aug 2026 baseline |
| Post-install harness pass rate | > 90% on recommended hardware |
| GUI harness visibility | Last 10 runs visible |

## What NOT to build in Phase 6

- Another planning layer for code
- Code Canvas buffer revival
- Cloud-first features without opt-in
- LSP integration (defer unless user demand)
- Competing with Cursor on inline completions

## Risks & open questions

| Item | Notes |
|------|-------|
| Harness flakiness at scale | More scenarios = more maintenance |
| GUI scope creep | Harness panel can be CLI-only initially |
| Git tools on Windows | Test `git_diff` on win32 |
| Cross-mode recipes | Complexity — start with docs-only handoff |

## Suggested priority order

1. Harness expansion (6.1) — highest ROI for confidence
2. Harness gate tiers (6.1) — smoke vs full
3. Packaged install gate (6.4) — user trust
4. Research recipes (6.3) — differentiation
5. GUI reports (6.2) — polish
6. Git tools (6.5) — nice to have

## Verification

```bash
./scripts/harness_gate.sh --tier full
python -m pytest agent/tests/ -q -k "harness or parity"
```
