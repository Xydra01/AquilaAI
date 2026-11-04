# Implementation Plan: M4 — AgentLoop, ContextCondenser, OrchestratorModule, RuntimeTierConfig

## Overview

M4 wires the M1 value types, the M2 inference backend, and the M3 stateful modules
into a single-threaded, deterministic agent loop that drives an LLM through one
module action per turn until a recipe's deterministic exit gate passes or the turn
limit is hit.

The plan builds the five new C++ components in dependency order — `RuntimeTierConfig`
(the single source of all thresholds), the independent `RunRecord` value type, the
`ContextCondenser` (which reads tier limits), the `OrchestratorModule` (which owns the
scratchpad), the `ReplayBackend` test double, and finally the `AgentLoop` (which wires
everything together) — then the `code_smoke_file` recipe cartridge, and closes with
full verification: the 21 correctness properties as property-based tests, Python oracle
fixtures, the live 3/3 and forced-failure runs, and the R20 / RECON_MAP 8.4 accounting.

Every new header lands under `src/core/include/aquila/agent/`, every source under
`src/core/agent/` and is added to the `aquila_core` static library in
`src/core/CMakeLists.txt`; every unit test lands in `tests/unit/` (Catch2WithMain) and
is listed in `tests/unit/CMakeLists.txt`. Property-based tests use a header-only PBT
library (RapidCheck's Catch integration), run a minimum of 100 iterations, are tagged
`// Feature: m4-agent-loop, Property {N}: {property_text}`, and run over a `ReplayBackend`
and a temp workspace so CI stays network-free and deterministic.

## Tasks

- [x] 1. Add the RapidCheck PBT dependency and the agent component directory scaffolding
  - Add RapidCheck (header-only, Catch2 integration) to `cmake/AquilaDeps.cmake` so it is available to the unit test target without a network at build time
  - Create the empty `src/core/agent/` source directory and `src/core/include/aquila/agent/` header directory, and the `src/core/agent/recipes/` resource directory
  - Link the RapidCheck Catch integration into `aquila_unit_tests` in `tests/unit/CMakeLists.txt` so later property tests compile on every lane
  - _Requirements: 8.3, 8.5_

- [x] 2. Implement RuntimeTierConfig (foundational — single source of all thresholds)
  - [x] 2.1 Implement `RuntimeTierConfig`, `TierLimits`, and `UniversalFlags`
    - Create `src/core/include/aquila/agent/runtime_tier.hpp` with `TierLimits{condense_threshold, rolling_tools, tool_output_chars, max_thought_tokens, gpu_layers, max_turns=16}` and `UniversalFlags{kv_rollback=false, gbnf=false, ngram=false}`
    - Create `src/core/agent/runtime_tier.cpp` implementing `for_profile(ComputeProfile)` with the exact tier values — `cpu_low_spec_edge`/`cpu_moe_fast`: 2048 / 2 / 1500 / 45 / 0; `gpu_high_vram`: 6144 / 4 / 4500 / 150 / 999 — and `default_config()` returning the `cpu_low_spec_edge` CPU tier (CPU-first; GPU is an explicit boost)
    - Universal flags are present on every tier and report `false` on the Ollama scaffold so M5 can flip them without a config change
    - Add `agent/runtime_tier.cpp` to the `aquila_core` library in `src/core/CMakeLists.txt`
    - _Requirements: 4.1, 4.2, 4.3_

  - [x]* 2.2 Write unit tests for the tier table, CPU-first default, and universal flags
    - Create `tests/unit/runtime_tier_test.cpp` (add to `tests/unit/CMakeLists.txt`) asserting the exact value table per `ComputeProfile`, that `default_config()` is a CPU tier and GPU is not the default, and that `UniversalFlags` are present and all `false` on the scaffold
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 3. Implement RunRecord value type (independent, canonical JSON)
  - [x] 3.1 Implement `RunRecord` with canonical serialization
    - Create `src/core/include/aquila/agent/run_record.hpp` with `RunRecord{task_id, mode, instance_id, step_index, ground_truth, last_interaction}` (defaulted `operator==`) and free `to_json(Json&, const RunRecord&)` / `from_json(const Json&, RunRecord&, const std::string& path)`
    - Create `src/core/agent/run_record.cpp` reusing the M1 `ToolInteraction` serializer for `last_interaction`, with `from_json` throwing `SchemaError` with a JSON-pointer path on malformed input
    - Add `agent/run_record.cpp` to the `aquila_core` library in `src/core/CMakeLists.txt`
    - _Requirements: 6.1, 6.4_

  - [x]* 3.2 Write property test for run-record round-trip
    - Create `tests/unit/run_record_test.cpp` (add to `tests/unit/CMakeLists.txt`)
    - **Property 20: Run record round-trip** — `parse<RunRecord>(to_canonical_string(r)) == r` and re-serialization is byte-identical
    - **Validates: Requirements 6.4**

  - [x]* 3.3 Write unit test for run-record field population and scratchpad separation
    - In `run_record_test.cpp`, assert all D12 fields populate and that run-record session fields are distinct from `AgentScratchpad` fields (fresh-start, no `run_state.json` import)
    - _Requirements: 6.1, 6.3_

- [x] 4. Implement ContextCondenser (three segments, ring buffer, spill, wipe)
  - [x] 4.1 Implement the condenser structure, pinned prefix, anchored block, and `build_messages`
    - Create `src/core/include/aquila/agent/context_condenser.hpp` with `SpillEntry`, the segment state, and the public API (`set_pinned_prefix`, `set_anchored`, `record_tool_cycle`, `push_guidance`, `build_messages`, `estimate_prompt_tokens`, `should_condense`, `condense`, `resolve_spill`)
    - Create `src/core/agent/context_condenser.cpp`; implement the constructor taking `TierLimits`, `set_pinned_prefix`, `set_anchored`, and `build_messages()` emitting pinned prefix first, then anchored block, then the rolling tail in recorded order
    - Add `agent/context_condenser.cpp` to the `aquila_core` library in `src/core/CMakeLists.txt`
    - _Requirements: 2.1_

  - [x] 4.2 Implement the rolling-tail ring buffer and head+tail spill
    - Implement `record_tool_cycle` as a ring buffer capped at `limits.rolling_tools`, dropping the oldest when full
    - Implement `head_tail_truncate`: when an output exceeds `tool_output_chars`, store a head+tail view embedding a stable spill reference, put the full text in `spill_`, and make `resolve_spill(ref)` return it; store short outputs verbatim with no spill
    - Implement `push_guidance` for corrective/guidance messages appended to the tail region without a tool cycle
    - _Requirements: 2.2, 2.3_

  - [x] 4.3 Implement token estimation, condense threshold, and wipe
    - Implement `estimate_prompt_tokens()` using the M3 `estimate_tokens` `ceil(chars/4)` heuristic over `build_messages()`
    - Implement `should_condense()` true exactly when `estimate_prompt_tokens() >= limits.condense_threshold`
    - Implement `condense()`: leave the pinned prefix unchanged, refresh the anchored block from the most recent `set_anchored` inputs, clear the rolling tail, returning evicted interactions
    - _Requirements: 2.4, 2.5, 2.6_

  - [x]* 4.4 Write property test for segment ordering
    - Create `tests/unit/context_condenser_test.cpp` (add to `tests/unit/CMakeLists.txt`)
    - **Property 6: Segment ordering** — `build_messages()` emits pinned prefix, then anchored block, then rolling tail in recorded order; pinned-prefix messages equal the set system prompt and recipe schema
    - **Validates: Requirements 2.1**

  - [x]* 4.5 Write property test for the rolling-tail ring buffer
    - **Property 7: Rolling tail holds exactly the last K interactions** — after recording M interactions the tail holds exactly the last `min(M, K)` in order and never exceeds K
    - **Validates: Requirements 2.2**

  - [x]* 4.6 Write property test for oversized-output truncation and spill
    - **Property 8: Oversized outputs truncate with a recoverable spill** — outputs over `tool_output_chars` yield a bounded tail view embedding a spill ref whose `resolve_spill(ref)` returns the full text; shorter outputs stored verbatim with no spill
    - **Validates: Requirements 2.3**

  - [x]* 4.7 Write property test for the wipe policy
    - **Property 9: Wipe preserves the prefix, refreshes the anchor, clears the tail** — after `condense()` the pinned prefix is unchanged, the anchored block equals the latest scratchpad/snapshot rendering, and the tail is empty
    - **Validates: Requirements 2.4**

  - [x]* 4.8 Write property test for the condense threshold boundary
    - **Property 10: Condense threshold is a monotone boundary** — `should_condense()` is true exactly when `estimate_prompt_tokens() >= condense_threshold`
    - **Validates: Requirements 2.6**

  - [x]* 4.9 Write property test for tier-driven condenser behavior
    - **Property 14: Behavior follows tier limits, not hardcoded constants** — two tiers differing in `rolling_tools`/`condense_threshold` change the tail cap and `should_condense()` boundary accordingly
    - **Validates: Requirements 4.4**

- [ ] 5. Checkpoint - Ensure all tests pass for the foundational value types and condenser
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement OrchestratorModule (owns the scratchpad, completion gate intents)
  - [x] 6.1 Implement the module skeleton, action schemas, configure, and snapshot round-trip
    - Create `src/core/include/aquila/agent/orchestrator_module.hpp` extending `ModuleBase`, owning `AgentScratchpad pad_`, with `module_id()=="OrchestratorModule"`, the `Intent` enum, and the host API (`scratchpad()`, `scratchpad_valid()`, `missing_fields()`, `take_intent()`)
    - Create `src/core/agent/orchestrator_module.cpp`; implement `get_actions()` exposing exactly `checkpoint_notes`, `trigger_context_condense`, `complete_recipe` with JSON-schema object parameters; `configure(initial_state)` reading `required_fields`/`checklist`; `export_state_snapshot`/`restore_state_snapshot` round-tripping scratchpad + checklist byte-equal
    - Add `agent/orchestrator_module.cpp` to the `aquila_core` library in `src/core/CMakeLists.txt`
    - _Requirements: 3.1, 3.5_

  - [x] 6.2 Implement the three actions and intent coordination
    - Implement `checkpoint_notes`: merge supplied fields into `pad_`; return `fail("missing_required_field", ...)` leaving required-field state unchanged when a recipe-required field is empty
    - Implement `trigger_context_condense`: validate the scratchpad first and only set `Intent::condense_requested` on success, otherwise return a failed `ActionResult` and no intent
    - Implement `complete_recipe`: record `completion_output_` and set `Intent::completion_requested` (the loop, not the module, runs the hook)
    - Route the actions through the protected `run(action_name, args)` dispatcher
    - _Requirements: 3.2, 3.3, 3.4_

  - [x] 6.3 Register OrchestratorModule as a built-in
    - Register `OrchestratorModule` alongside `WorkspaceModule` and `ExecutionModule` in `src/core/modules/builtin.cpp` under id `"OrchestratorModule"` so recipes load it and `ModuleRegistry::validate_recipe` can resolve it
    - _Requirements: 3.1_

  - [x]* 6.4 Write property test for checkpoint validation and merge
    - Create `tests/unit/orchestrator_module_test.cpp` (add to `tests/unit/CMakeLists.txt`)
    - **Property 11: Checkpoint validates required fields and merges on success** — success exactly when every required field is present and non-empty; on success the scratchpad reflects updates, on failure `error_code == "missing_required_field"` and required-field state is unchanged
    - **Validates: Requirements 3.2**

  - [x]* 6.5 Write property test for condense-gating
    - **Property 12: Condense is requested only after scratchpad validation** — `trigger_context_condense` yields `condense_requested` exactly when validation passes; otherwise a failed `ActionResult` and no intent
    - **Validates: Requirements 3.3**

  - [x]* 6.6 Write property test for the scratchpad snapshot round-trip
    - **Property 13: Scratchpad snapshot round-trip** — export, restore into a fresh module, export again yields byte-identical JSON
    - **Validates: Requirements 3.5**

  - [x]* 6.7 Write unit test for the action set and completion intent
    - In `orchestrator_module_test.cpp`, assert `get_actions()` exposes exactly the three actions with object schemas (3.1) and that `complete_recipe` sets `completion_requested` with the completion output (3.4)
    - _Requirements: 3.1, 3.4_

- [x] 7. Implement the ReplayBackend test double
  - [x] 7.1 Implement the scripted `IInferenceBackend`
    - Create `tests/unit/replay_backend.hpp` implementing `IInferenceBackend`: `append` records context for assertions, `generate` pops the next scripted `GenerationResult`, `mark_checkpoint`/`rollback_to` track context position, `active_profile()` returns the configured profile, and `supports_kv_reuse()` returns `false` to mirror the Ollama scaffold
    - _Requirements: 8.3_

- [x] 8. Implement AgentLoop (the deterministic driver and exit gate)
  - [x] 8.1 Implement the loop skeleton, recipe load/validation, and generation params
    - Create `src/core/include/aquila/agent/agent_loop.hpp` with `LoopOutcome`, `TurnRecord`, `TerminalResult`, `LoopConfig`, and `AgentLoop` (ctor takes `IInferenceBackend&`, `const ModuleRegistry&`, `ModuleContext`)
    - Create `src/core/agent/agent_loop.cpp`; implement `run(...)` to load and `validate_recipe` (SchemaError at load time), build the module set, create the per-run `RunRecord`, seed the condenser's pinned prefix, and set up `generation_params` with `OutputConstraint::json_schema(action_call_schema())` and the `max_thought_tokens`-derived budget
    - Implement `action_call_schema()` returning the `{thought, module, action, args}` JSON Schema (required, `additionalProperties:false`) matching M1 `ActionCall`
    - Add `agent/agent_loop.cpp` to the `aquila_core` library in `src/core/CMakeLists.txt`
    - _Requirements: 1.1, 1.2, 5.4_

  - [x] 8.2 Implement the deterministic turn cycle with parse recovery and error-code surfacing
    - Each turn: `build_messages()` → `rollback_to(0)` + append (scaffold has no KV reuse) → `generate` → `parse<ActionCall>` in try/catch
    - On parse failure record `TurnRecord{parsed=false}`, `push_guidance(corrective)`, and advance one turn without throwing
    - Resolve module/action; for unknown module, action not loaded, or action not exposed, build a synthetic failed `ActionResult` with `error_code` (`unknown_module`, `action_not_exposed`) and surface it, branching only on `success`/`error_code` and never on `llm_facing_output` text
    - Dispatch exactly one `execute_action`, wrap as a `ToolInteraction`, call `record_tool_cycle`, and update `RunRecord` (`step_index`, `last_interaction`); treat a backend `GenerationResult{ok==false}` as a failed turn that records the backend error and continues
    - _Requirements: 1.2, 1.3, 1.4, 6.2_

  - [x] 8.3 Implement orchestrator-intent handling, condense coordination, and turn-limit terminal
    - After dispatch, read the Orchestrator `Intent`: on `condense_requested` run `condenser.condense()` (validation already enforced by the module); on `completion_requested` run the exit gate
    - After each turn, if `condenser.should_condense()` perform a wipe (after scratchpad validation)
    - Stop at `limits.max_turns`, returning `TerminalResult{outcome=turn_limit, success=false}` with the full `TurnRecord` transcript and `RunRecord`
    - _Requirements: 1.5, 2.6, 3.3_

  - [x] 8.4 Implement the recipe exit gate (`run_exit_gate`)
    - When `complete_recipe` is requested: if the recipe has no `post_llm_validation_hook`, return `TerminalResult{success=true}` with the completion output
    - If a hook exists, run it as a deterministic `HookCall` through the registry (not an LLM turn, no backend generation), allowing hook actions outside `expose_actions`
    - On hook success return `TerminalResult{success=true}` with the completion output; on `must_succeed` failure inject `on_failure_instruction` as next-turn guidance and continue the loop
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [x]* 8.5 Write property test for one action per valid turn
    - Create `tests/unit/agent_loop_test.cpp` (add to `tests/unit/CMakeLists.txt`), driven by `replay_backend.hpp` over a temp workspace
    - **Property 1: One action dispatched per valid turn** — each turn executes exactly one `execute_action` and appends exactly one `ToolInteraction` to the transcript and tail
    - **Validates: Requirements 1.2**

  - [x]* 8.6 Write property test for parse-failure recovery
    - **Property 2: Parse failures never throw and always advance a turn** — a reply failing `parse<ActionCall>` records `parsed==false`, appends corrective guidance, advances one turn, and never throws
    - **Validates: Requirements 1.3**

  - [x]* 8.7 Write property test for error-code-driven classification
    - **Property 3: Outcome classification is error_code-driven only** — failed dispatch yields non-empty `error_code` and control flow depends only on `success`/`error_code`, never on `llm_facing_output` text
    - **Validates: Requirements 1.4**

  - [x]* 8.8 Write property test for turn-limit termination
    - **Property 4: Turn limit terminates as non-success** — a backend that never completes stops after exactly `max_turns` with `TerminalResult{outcome==turn_limit, success==false}`
    - **Validates: Requirements 1.5**

  - [x]* 8.9 Write property test for determinism
    - **Property 5: Determinism — identical inputs yield byte-identical transcripts** — two runs with the same recipe, request, and replay script produce byte-identical transcripts and run records via canonical serialization
    - **Validates: Requirements 1.6**

  - [x]* 8.10 Write property test for the exit gate being a deterministic module call
    - **Property 15: The exit gate is a deterministic module call, not an LLM turn** — attempting `complete_recipe` invokes the hook module/action exactly once through the registry with no backend generation during the gate
    - **Validates: Requirements 5.1**

  - [x]* 8.11 Write property test for completion-gate outcome
    - **Property 16: Completion succeeds exactly when the gate passes** — completion returns `success==true` with output exactly when the hook is absent or passes; a failing `must_succeed` hook does not exit and injects `on_failure_instruction`
    - **Validates: Requirements 5.2, 5.3**

  - [x]* 8.12 Write property test for run-record advance and memory separation
    - **Property 19: Session fields advance in the run record and never leak into memory** — after each turn `step_index` increments and `last_interaction` updates, and no run-record session field appears in the `AgentScratchpad`
    - **Validates: Requirements 6.2**

  - [x]* 8.13 Write unit test for the synchronous single-threaded contract
    - In `agent_loop_test.cpp`, assert the loop runs synchronously on one thread with all turn state owned by the frame or condenser (no async/coroutines)
    - _Requirements: 1.1_

- [ ] 9. Checkpoint - Ensure all tests pass for the loop, modules, and condenser
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement the code_smoke_file recipe cartridge
  - [x] 10.1 Author the recipe JSON and header accessor
    - Create `src/core/agent/recipes/code_smoke_file.recipe.json` as a canonical `RecipeCartridge`: `load_modules` = `WorkspaceModule`, `ExecutionModule`, `OrchestratorModule`; `expose_actions` = Workspace `create_file`/`surgical_edit`, Orchestrator `checkpoint_notes`/`complete_recipe`; a `scratchpad_checklist` of required fields; and a `post_llm_validation_hook{must_succeed:true, on_failure_instruction:...}` that checks a file matching `**/harness_smoke.py` exists and contains `HARNESS_OK`
    - Create `src/core/include/aquila/agent/recipes.hpp` with a header-only `code_smoke_file_recipe()` accessor returning the parsed `RecipeCartridge` (no run-time file I/O)
    - _Requirements: 7.1, 7.2, 7.5_

  - [x]* 10.2 Write unit test for cartridge load, validation, and JSON parity
    - Create `tests/unit/recipe_cartridge_test.cpp` (add to `tests/unit/CMakeLists.txt`): assert `code_smoke_file_recipe()` parity-matches the on-disk JSON, that `ModuleRegistry::validate_recipe` passes, and that the hook names an action outside `expose_actions` (allowed for a `HookCall`)
    - _Requirements: 7.1, 5.5_

  - [x]* 10.3 Write property test for hooks invoking actions the LLM cannot
    - In `recipe_cartridge_test.cpp` / `agent_loop_test.cpp`
    - **Property 18: Hooks may invoke actions the LLM cannot** — a `HookCall` runs an action present on a loaded module but absent from `expose_actions`, while an LLM dispatch of the same action is rejected with `error_code == "action_not_exposed"`
    - **Validates: Requirements 5.5**

  - [x]* 10.4 Write property test for load-time hook validation
    - **Property 17: Invalid hook references fail at load time** — a recipe whose hook names a module not in `load_modules` or an action no loaded module exposes throws `SchemaError` with a non-empty JSON-pointer path; a valid recipe does not throw
    - **Validates: Requirements 5.4**

  - [x]* 10.5 Write property test for the permanently-failing gate
    - **Property 21: A permanently failing gate never reports success** — a forced-failure scenario where the hook can never pass never returns success and ends `{outcome==turn_limit, success==false}`
    - **Validates: Requirements 7.4**

- [x] 11. Add Python oracle fixtures for token estimate and tail-keep parity
  - [x] 11.1 Extend the fixture generator and add the oracle comparison test
    - Extend `tests/fixtures/python/gen_python_fixtures.py` (pinned `759212a`) to emit `estimate_messages_tokens` fixtures (prefix `messages_estimate_`) and `_keep_recent_turns` fixtures under `tests/fixtures/python/`; regeneration must leave `git status` clean
    - Add oracle cases to `tests/unit/python_oracle_test.cpp` asserting `estimate_prompt_tokens`/`estimate_tokens` agree with the Python token estimate within rounding, and the ring buffer keeps the same last-K set as `_keep_recent_turns`
    - _Requirements: 8.2, 2.5_

- [x] 12. Add live end-to-end and forced-failure tests (excluded from CI)
  - [x] 12.1 Implement the live code_smoke_file and forced-failure runs
    - Add a test under `tests/live/` (listed in `tests/live/CMakeLists.txt`, excluded from CI per the M2 policy) running `code_smoke_file` against stock Ollama 3 times, asserting a file matching `**/harness_smoke.py` exists and contains `HARNESS_OK`, recording turn count and acceptance result
    - Add the forced-failure live run (fault-injection build that omits `HARNESS_OK`) asserting the loop reaches the turn limit with a non-success terminal
    - _Requirements: 7.2, 7.3, 7.4, 8.4_

- [ ] 13. Verify all five build lanes, sanitizers, and complete R20 / RECON_MAP accounting
  - [ ] 13.1 Verify build lanes and sanitizers clean
    - Build and run the unit suite on all five lanes (`msvc-release`, `msvc-asan`, `msvc-release-cuda`, `mingw-san`, `linux-san`) and the three CI jobs on a fresh clone, confirming ASan/UBSan/LSan report nothing and all new sources/tests compile into `aquila_core` and `aquila_unit_tests`
    - _Requirements: 8.1, 8.5_

  - [ ] 13.2 Record the R20 line-count accounting and RECON_MAP 8.4 verdicts
    - Measure the C++ LOC added by the five components versus the Python they replace (`code_agent.py` ~230, `context_manager.py` ~260, `run_state.py` session portion, `context_budget.py` tiers) and add a RECON_MAP section 8.4 with per-feature verdicts against Python; if C++ is not smaller, state why (R20)
    - _Requirements: 8.6_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks (unit, property, integration) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references the specific requirement clauses it implements for traceability.
- Property-based tests use RapidCheck's Catch2 integration, run a minimum of 100 iterations, are tagged `// Feature: m4-agent-loop, Property {N}: {property_text}`, and run over a `ReplayBackend` and a per-case temp workspace so CI stays network-free and deterministic.
- All 21 correctness properties from the design are mapped: P1–P5 (loop: tasks 8.5–8.9), P6–P10 (condenser: tasks 4.4–4.8), P11–P13 (orchestrator: tasks 6.4–6.6), P14 (tier-driven: task 4.9), P15–P18 (exit gate: tasks 8.10–8.11, 10.3–10.4), P19–P20 (run record: tasks 8.12, 3.2), P21 (forced-failure: task 10.5).
- Live tests (network/Ollama) are excluded from CI, matching the M2 live-test policy; their CI-safe deterministic counterpart is Property 21 via the replay backend.
- Checkpoints ensure incremental validation at reasonable breaks.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2.1", "3.1", "7.1"] },
    { "id": 1, "tasks": ["2.2", "3.2", "3.3", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3"] },
    { "id": 3, "tasks": ["4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3"] },
    { "id": 5, "tasks": ["6.4", "6.5", "6.6", "6.7", "8.1"] },
    { "id": 6, "tasks": ["8.2"] },
    { "id": 7, "tasks": ["8.3", "8.4"] },
    { "id": 8, "tasks": ["8.5", "8.6", "8.7", "8.8", "8.9", "8.10", "8.11", "8.12", "8.13", "10.1"] },
    { "id": 9, "tasks": ["10.2", "10.3", "10.4", "10.5", "11.1"] },
    { "id": 10, "tasks": ["12.1", "13.1"] },
    { "id": 11, "tasks": ["13.2"] }
  ]
}
```
