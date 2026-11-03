# Phase 4: Unified Agent Loop

**Status:** Not started  
**Estimate:** 2–3 weeks  
**Depends on:** [Phase 1](phase-1-enterprise-code-tools.md), [Phase 3](phase-3-slim-the-os.md)  
**Blocks:** [Phase 6](phase-6-aquila-advantages.md)

## Goal

One loop implementation (~300 lines) with pluggable executors. Retire the monolithic `LoopEngine` for act turns.

## Problem

`loop_engine.py` is ~5,600 lines mixing:
- Capability act dispatch
- Legacy tool act path
- Step FSM, coaches, repetition guards
- Research-specific URL registry, source registry
- Code TDD (being removed in Phase 3)
- Parallel tool execution, episode budgets, run state

Code already bypasses this. Research still depends on it. Maintaining two loops guarantees drift.

## Target architecture

```
agent/core/agent_loop.py
├── AgentLoop.run(messages, executor, max_turns, ...)
├── ToolExecutor          → code_agent_tools
└── CapabilityExecutor  → registry.run_capability

agent/core/plan_runner.py  (~200 lines)
└── for step in plan.steps:
        AgentLoop.run(allowlist=step_caps, max_turns=step.max_iterations)
```

## Deliverables

### 4.1 — Core loop module

- [ ] New: `agent/core/agent_loop.py`
  - `AgentLoopResult` dataclass: `summary`, `turns`, `messages`, `metrics`
  - `AgentLoop.run()`:
    1. Estimate tokens
    2. `client.chat(format=schema, ...)`
    3. Parse response (`parse_agent_response` or unified parser)
    4. `executor.execute(name, args)` → formatted output
    5. Append to messages
    6. Stop on: cancel, max turns, executor signals done
  - Surface param: `chat` | `act`
  - Thinking callback support

### 4.2 — Executors

- [ ] New: `agent/core/executors/tool_executor.py`
  - Maps tool name → `code_agent_tools` function
  - Validates args (lightweight or Pydantic models per tool)
  - Returns formatted string for LLM

- [ ] New: `agent/core/executors/capability_executor.py`
  - Maps cap ID → `run_capability`
  - Optional allowlist filter
  - `heal_capability_call` hook (research only, behind flag)
  - `format_capability_result_for_llm`

### 4.3 — Schema builders (unify)

- [ ] `agent/parser/action_schema.py` — **New** or extend `structured_schema.py`
  - `build_tool_action_schema(tool_names)` 
  - `build_capability_action_schema(cap_ids)` 
  - Shared response shape: `reasoning`, `tool` OR `capabilities[]`, `final_report`

### 4.4 — Thin plan runner for batch modes

- [ ] New: `agent/core/plan_runner.py`
  - Input: `plan.json`, mode, agent
  - For each step:
    - Resolve allowlist from `adapters.allowed_capabilities_for_step`
    - Run `AgentLoop` with `CapabilityExecutor`
    - Advance ledger / milestones via existing `loop_objectives` hooks
  - No inline FSM — step advancement is Python for-loop

### 4.5 — Migrate research act path

- [ ] `mode_runner.py` / `main.py`: research act → `plan_runner` + `AgentLoop`
- [ ] Port essential pieces from `LoopEngine`:
  - [ ] URL visit registry (research)
  - [ ] Source registry
  - [ ] Coach / repeat guard → `agent/core/loop_guards.py` (optional module)
  - [ ] Run state injection → keep `run_state.py` integration
- [ ] **Do not port:** legacy tool-act path, code TDD, parallel tool fan-out (unless needed)

### 4.6 — Migrate writing / learn act path

- [ ] Writing: linear plan steps → `plan_runner`
- [ ] Learn syllabus build: same pattern
- [ ] Character build: same pattern

### 4.7 — Retire LoopEngine

- [ ] Mark `LoopEngine` deprecated
- [ ] Feature flag: `AQUILA_USE_AGENT_LOOP=1` (default 0 until parity)
- [ ] Flip default when research parity tests pass
- [ ] Delete `loop_engine.py` when <200 lines remain or fully unused

### 4.8 — Tests

- [ ] `agent/tests/test_agent_loop.py` — mock client + executor
- [ ] `agent/tests/test_plan_runner.py` — multi-step mock plan
- [ ] All existing parity tests must pass:
  - `test_research_capability_parity.py`
  - `test_writing_capability_parity.py`
  - `test_learn_capability_parity.py`
  - `test_code_agent_loop.py`

## Files to touch

| File | Change |
|------|--------|
| `agent/core/agent_loop.py` | **New** |
| `agent/core/plan_runner.py` | **New** |
| `agent/core/executors/tool_executor.py` | **New** |
| `agent/core/executors/capability_executor.py` | **New** |
| `agent/core/loop_guards.py` | **New** (extract coach/repeat) |
| `agent/core/loop_engine.py` | Shrink / delete |
| `agent/core/mode_runner.py` | Wire new loop |
| `agent/core/main.py` | Wire new loop |
| `agent/parser/structured_schema.py` | Unified schema builders |

## Exit criteria

- [ ] Code mode uses `AgentLoop` + `ToolExecutor` only
- [ ] Research mode uses `AgentLoop` + `CapabilityExecutor` via `plan_runner`
- [ ] `loop_engine.py` unused or <1,500 lines
- [ ] Full parity test suite green
- [ ] Harness matrix (code + research + writing) green on gated model

## Line count targets

| Module | Target |
|--------|--------|
| `agent_loop.py` | < 350 lines |
| `plan_runner.py` | < 250 lines |
| `tool_executor.py` | < 150 lines |
| `capability_executor.py` | < 200 lines |
| `loop_guards.py` | < 300 lines |

## Risks & open questions

| Item | Notes |
|------|-------|
| Research parallel searches | LoopEngine may parallelize; verify if needed |
| Run state / digest compression | Must port without behavior change |
| MCP act paths | Audit `mcp_bridge` for LoopEngine assumptions |
| Big-bang vs flag flip | **Recommend:** flag per mode (code first, then research) |
| Episode budgets / checkpoint nudges | Port to `loop_guards` or drop if unused |

## Migration order

1. Code: `code_agent.py` → `AgentLoop` + `ToolExecutor` (thin refactor)
2. Writing: simplest linear plan
3. Learn / character
4. Research: most complex; last

## Out of scope

- New capabilities or tools
- GUI redesign
- Model fine-tuning (Phase 5)

## Verification

```bash
AQUILA_USE_AGENT_LOOP=1 ./scripts/harness_gate.sh
python -m pytest agent/tests/test_research_capability_parity.py agent/tests/test_writing_capability_parity.py -q
```
