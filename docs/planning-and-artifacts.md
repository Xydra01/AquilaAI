# Planning and task artifacts (Track B)

Antigravity-style **plan workshop** and **walkthrough** artifacts for task modes.

## Lifecycle

1. User submits task → planner or micro-plan generates `plan.json`
2. **Plan review** (GUI) — approve, revise with feedback, or cancel
3. Act loop executes against `ledger.json`
4. On `finish_task` → `walkthrough.md` + `reflection.json` + enriched episodic memory

## Artifact layout

Under `Agent-Tasks/{task_id}/` (research: `Agent-Plans/{task_id}/`):

| File | Purpose |
|------|---------|
| `ledger.json` | Execution state |
| `plan.json` | Machine plan |
| `plan.md` | Human-readable plan for review |
| `walkthrough.md` | Post-run what / why / how to verify |
| `reflection.json` | Structured reflection for recall |
| `artifacts/` | Delegation results, deliverables |

Legacy flat `Agent-Tasks/{task}.json` files are migrated on first access.

## Environment

| Variable | Default | Role |
|----------|---------|------|
| `AQUILA_PLAN_REVIEW` | `1` | Pause for user approval before act loop |
| `AQUILA_PLAN_AUTO_APPROVE_MICRO` | `0` | Skip review for micro-plans |
| `AQUILA_WALKTHROUGH` | `1` | Generate walkthrough on finish |
| `AQUILA_DYNAMIC_LOOP` | `0` | Milestone-first planner for research when `1` (also disables micro-plan fast path) |

Harness / CI: set `AQUILA_PLAN_REVIEW=0` to auto-approve.

## GUI

- **Plan review dialog** — Approve & Run, Revise (feedback → `revise_task_plan`), Cancel
- **Task workspace** — milestones list, Walkthrough tab after completion

## API (Agent)

- `approve_and_run_task(task_name, user_request, mode, ...)`
- `revise_task_plan(task_name, user_request, mode, feedback)`

Returns `__AQUILA_AWAITING_PLAN_APPROVAL__|{task}|{mode}` when review is required.

## Episodic memory

`store_experience` metadata includes `walkthrough_path`, `deliverable_path`, `plan_approach`, `user_verified`.

## Tester checklist

1. Start a research or task run with `AQUILA_PLAN_REVIEW=1`
2. Confirm plan dialog appears before tools run
3. Revise with feedback → plan version increments
4. Approve → act loop runs
5. On completion, open **Walkthrough** tab
6. Confirm `Agent-Tasks/{task}/walkthrough.md` exists

## Tests

```bash
cd agent && python -m pytest tests/test_plan_artifact.py tests/test_plan_review_gate.py tests/test_walkthrough_artifact.py -q
```

See [constrained-decoding.md](constrained-decoding.md) and [workflow-editor-vision.md](workflow-editor-vision.md).
