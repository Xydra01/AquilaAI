# Dynamic (milestone-driven) act loop

Cursor-style task execution: one **work** phase with a mode-wide tool palette, milestone progress in prompts, and early `finish_task` when objective evidence exists. Legacy rigid pipelines remain available for comparison and regression.

## Enable

```bash
export AQUILA_DYNAMIC_LOOP=1
# optional
export AQUILA_AUTO_ADVANCE_MILESTONES=1   # default on
export AQUILA_TASK_EPISODE_MAX=32
export AQUILA_TASK_WEB_SEARCH_CAP=12
```

Set `AQUILA_DYNAMIC_LOOP=0` (default) to restore step-kind tool prisons and per-step forced advances.

## Behavior vs legacy

| Legacy | Dynamic |
|--------|---------|
| `search` → `read` → `synthesize` → `finalize` ledger rows | Often **work** + **finalize** (2 rows) |
| `STEP_KIND_TOOLS` intersection per step | `WORK_PALETTE[mode]` + denylist only |
| Hard advance at step `max_iterations` | Soft step limit; hard stop at **task** episode budget |
| `finish_task` blocked until final index | Allowed on final step when milestones + `final_report` |
| Coach hints cite phase names | Coach hints cite milestones |

Character build and learn syllabus modes stay on strict step policies even when the flag is on.

## Modules

- [`agent/core/loop_settings.py`](../agent/core/loop_settings.py) — env flags and caps
- [`agent/core/loop_objectives.py`](../agent/core/loop_objectives.py) — `MilestoneTracker`, per-mode checklist
- [`agent/policies/tool_catalog.py`](../agent/policies/tool_catalog.py) — `WORK_PALETTE`, dynamic branch in `allowed_tools_for_step`
- [`agent/core/plan_validator.py`](../agent/core/plan_validator.py) — `expand_dynamic_*_plan` templates
- [`agent/core/fast_path.py`](../agent/core/fast_path.py) — micro-plan uses work+finalize when flag on
- [`agent/core/episode_tracker.py`](../agent/core/episode_tracker.py) — `TaskRunState` task-wide budget
- [`agent/core/loop_engine.py`](../agent/core/loop_engine.py) — palette, milestones, auto-advance, early finish

## JSONL events (harness / scorecard)

| Event | Meaning |
|-------|---------|
| `palette_mode` | Dynamic palette active (`dynamic: true`) |
| `milestone_update` | Per-turn milestone snapshot |
| `early_finish_eligible` | Final step milestones satisfied |
| `forced_advance` | OS advanced ledger (parse/iteration limit) |
| `premature_finish_blocked` | `finish_task` rejected before final step |

[`capability_scorecard.py`](../agent/core/capability_scorecard.py) aggregates `forced_advance_count`, `milestone_update_count`, `dynamic_loop_runs`. Rubrics may set `max_forced_advance_count: 0` and `require_finish: true` (see `code_smoke_file`).

## Harness

Run with dynamic loop for cleaner smoke metrics:

```bash
AQUILA_DYNAMIC_LOOP=1 AQUILA_HARNESS_FORCE_MICRO_PLAN=1 ../scripts/aquila-capability-run.sh code_smoke_file
```

See [aquila-recursive-harness.md](aquila-recursive-harness.md) and [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md).
