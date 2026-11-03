# Phase 3: Slim the OS



**Status:** Complete  

**Estimate:** 2 weeks (can overlap Phase 2)  

**Depends on:** [Phase 1](phase-1-enterprise-code-tools.md)  

**Blocks:** [Phase 4](phase-4-unified-agent-loop.md)



## Goal



Remove dual code architectures. One code path only. Stop maintaining FSM/plan/micro-plan logic for code mode.



## Deliverables



### 3.1 — Freeze LoopEngine for code



- [x] `LoopEngine` constructor / `run()` hard-fail when `mode == "code"`

- [x] `"code"` removed from `CAPABILITY_ACT_MODES`

- [x] Dead branches left in place with comments; production unreachable



### 3.2 — Remove code-specific FSM concepts



- [x] `should_micro_plan("code")` always False; explore brief off for code

- [x] Code capability allowlists return empty frozenset

- [x] `plan_needs_review(..., mode="code")` always False

- [x] TDD step kinds remain only as dead LoopEngine / archived plan JSON (not live)



### 3.3 — Deprecate Code Canvas as source of truth



- [x] Agent tools write direct to disk (Phase 1)

- [x] Keep `active_code_state.json` for GUI project metadata only

- [x] `cap.dev.sync_project` registered for MCP/compat; not in code agent tools



### 3.4 — Slim heal/coach for code



- [x] Code tool loop uses `_heal_tool_action` only (no `heal_calls`)

- [x] No `LoopCoach` import in `code_agent.py`



### 3.5 — GUI alignment



- [x] `gui.task_finished` / `_open_plan_review_dialog` skip `mode == "code"`

- [x] IDE sync button labeled as optional buffer sync



### 3.6 — Harness cleanup



- [x] Stale `cap.dev.*` scenario copy updated to tool names

- [x] Deleted `code_habit_tracker_scaffold` scenario

- [x] Gate set unchanged: `code_smoke_file`, `code_habit_tracker`



### 3.7 — Test cleanup



- [x] FSM LoopEngine(mode=code) tests deleted/rewritten/skipped

- [x] `code_chat.py` removed; tests import `code_agent`

- [x] `test_code_capability_parity` skipped (MCP caps still registered)



### 3.8 — Docs cleanup



- [x] [code-mode.md](../code-mode.md)

- [x] [planning-and-artifacts.md](../planning-and-artifacts.md)

- [x] [capability-modules-vision.md](../capability-modules-vision.md)



## Exit criteria



- [x] `LoopEngine(mode="code")` raises; research LoopEngine intact

- [x] Code task never opens plan review

- [x] No `sync_project` on code agent happy path

- [x] Phase 0 smoke gate re-run after ship — smoke **3/3** (`aquila:latest`, 2026-09-06)



## Out of scope



- Deleting entire `loop_engine.py` (Phase 4)

- Research/writing plan review changes

- Habit tracker 3/3 (Phase 5)

