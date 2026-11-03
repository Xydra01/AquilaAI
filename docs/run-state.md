# RunState — unified context management

Aquila maintains a **per-task RunState** (`TaskRunContext`) as the authoritative memory plane during act loops. It replaces scattered workspace-summary injection, ephemeral capability banners, and desynchronized checklist/milestone signals.

## Artifact

Each task stores state at:

```
Agent-Tasks/<task_id>/run_state.json
```

Research tasks use `Agent-Plans/<task_id>/run_state.json`.

The file is **persisted after every capability checkpoint** (atomic write via temp + rename).

## Two-tier summary model

| Layer | Scope | Update cadence | Consumer |
|-------|-------|----------------|----------|
| **Run digest** | Single task | Every capability | Think/act prompts (RUN STATE block) |
| **Instance workspace summary** | Cross-task per agent instance | Step advance rollup | Future tasks, instance profile |

The live prompt uses **RUN STATE**, not the instance `workspace_summary.md`. On step advance, the run digest rolls up into the instance summary via `rollup_run_digest_to_workspace()`.

## TaskRunContext fields

- `goal` — immutable user goal
- `goal_summary` — short distilled goal (used after episode 0)
- `run_digest` — rolling bullet narrative of capability outcomes
- `last_capability` — latest capability id, ok/fail, summary text
- `ground_truth` — mode-specific filesystem/artifact snapshot
- `checklist` — living plan checklist mirror
- `milestones` — milestone booleans from ground truth
- `episode`, `step_index` — loop cursor

## Checkpoint pipeline

After each capability in `loop_engine._execute_capability_batch`:

1. Update `last_capability` and append to `run_digest`
2. Snapshot **ground truth** via mode provider (`run_state_providers.py`)
3. **Auto-tick checklist** via `infer_completed_items()` + provider hints
4. Sync **milestones** via `apply_ground_truth_to_milestone_state()`
5. LLM-compress digest if over tier budget (when `AQUILA_RUN_DIGEST_COMPRESS=1`)
6. `persist()` → `run_state.json`

## Ground-truth providers

| Mode | Provider | Reads |
|------|----------|-------|
| code | `CodeGroundTruthProvider` | `Agent-Code/active_code_state.json` |
| writing | `WritingGroundTruthProvider` | `Agent-Drafts/active_draft_state.json` |
| research | `ResearchGroundTruthProvider` | scratchpad note count |
| learn | `LearnGroundTruthProvider` | course dir / syllabus.json |
| character | `CharacterGroundTruthProvider` | persona dir / initialization.md |

## Prompt contract

`TaskRunContext.build_turn_messages()` injects a single **RUN STATE** block via `context_manager.build_loop_messages(run_state_block=...)`.

**Goal injection policy:**

- Episode 0 / step entry: full `goal`
- Later episodes: `goal_summary` + `run_digest` (not full goal re-injection)

When `AQUILA_RUN_STATE_ENABLED=1` (default):

- Step entry no longer duplicates workspace summary
- `LAST CAPABILITY RESULT` banner in user messages is retired (last result is in RUN STATE)

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `AQUILA_RUN_STATE_ENABLED` | `1` | Use RunState for prompt assembly |
| `AQUILA_RUN_DIGEST_COMPRESS` | `1` | LLM-compress digest when over tier cap |

Digest and ground-truth char caps are set per context tier in `context_budget.py` (`run_digest_max_chars`, `ground_truth_max_chars`).

## Migration

Tasks without `run_state.json` bootstrap from `workspace_summary` + plan checklist on first load. Set `AQUILA_RUN_STATE_ENABLED=0` to fall back to legacy workspace-summary-only prompts.

## Module map

- `agent/core/run_state.py` — `TaskRunContext`, `DigestCompressor`, rollup helpers
- `agent/core/run_state_providers.py` — mode ground-truth adapters
- `agent/core/loop_engine.py` — load/init, checkpoint, `_assemble_loop_messages`
- `agent/policies/context_manager.py` — `build_loop_messages`, `on_step_advance` rollup hook
