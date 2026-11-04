# Requirements Document

**Spec:** M4 — AgentLoop, ContextCondenser, OrchestratorModule, RuntimeTierConfig

## Introduction

M4 is the orchestration milestone of the Aquila-cpp rebuild. M0-M3 built the
foundation (build/CI), the value types (M1), the inference backend (M2), and the
stateful modules with their canvas/firewall/diagnostics (M3). M4 wires those
pieces into a running agent: a single-threaded, deterministic loop that drives an
LLM through module actions until a recipe's exit gate is satisfied.

Scope, taken verbatim from the M4 row of `docs/recon/RECON_MAP.md` section 8:

> `AgentLoop` + `ContextCondenser` (3 segments, R6) + **OrchestratorModule** +
> `RuntimeTierConfig` (R16) + one code recipe cartridge with a
> `post_llm_validation_hook` + a **run record** for the session fields that are
> not LLM memory (`task_id`, `mode`, `instance_id`, `step_index`, `ground_truth`,
> last interaction; section 8.1, D12).

Proof of done, from the same row:

> Harness scenario `code_smoke_file` passes 3/3 on C++ (Python baseline 3/3 [doc]);
> the loop refuses to exit while the hook fails (forced-failure test).

### Governing principles (from RECON_MAP section 2.1)

- **R2** Single-threaded, deterministic, value-oriented core loop. No async, no
  coroutines. All data owned by `ContextCondenser` or the `AgentLoop` frame.
- **R6** Context condenser with three KV segments: `[0..P]` system prompt +
  active recipe schema (never evicted); `[P+1..S]` structured scratchpad + module
  state snapshots (evicted only on wipe); `[S+1..end]` rolling tail of the last
  2-3 tool/action results.
- **R7** Self-note is a strict schema (already realized as `AgentScratchpad`, M1).
- **R8** Pre-truncate oversized outputs before they enter the rolling tail
  (head+tail), spill the full output to a side buffer with a reference.
- **R11** OrchestratorModule actions: `checkpoint_notes`, `trigger_context_condense`,
  `complete_recipe`; validates required scratchpad fields before a wipe.
- **R12** Recipe cartridges with a `post_llm_validation_hook{must_succeed,
  on_failure_instruction}`; the loop refuses to exit while the hook fails.
- **R14** LLM action call = grammar-enforced JSON `{thought, module, action, args}`.
- **R16** CPU-first `RuntimeTierConfig`: universal flags + tier knobs (condense
  threshold 2048/6144, rolling tools 2/4, tool output chars 1500/4500, thought
  tokens 45/150, gpu layers 0/999).
- **R19** Improve, don't transliterate. Diverge from Python only to fix a concrete
  Python problem, and cite the evidence (file:line).
- **R20** Condense. Same behavior in less code, measured per milestone.

### Python parity oracles (pinned reference `759212a`)

M4 behavior is checked against these Python sources, which are the behavioral
reference (R5/R19), not a shape to copy:

- **Loop:** `agent/core/code_agent.py` `run_tool_session` (the "one dumb loop":
  model -> parse -> heal -> one tool -> append, 16-turn cap).
- **Condenser:** `agent/policies/context_manager.py` (`build_loop_messages`,
  `estimate_messages_tokens`, `_keep_recent_turns`, `on_step_advance`).
- **Tier knobs:** `agent/policies/context_budget.py` (`ContextProfile`, tier
  thresholds).
- **Run record / scratchpad analogue:** `agent/core/run_state.py`
  (`TaskRunContext`: task_id, mode, instance_id, step_index, ground_truth,
  last_capability).
- **Exit acceptance:** `agent/core/capability_harness.py` `code_smoke_file`
  scenario; acceptance `check_file_glob **/harness_smoke.py`, `file_contains
  HARNESS_OK`.

### Divergences already decided (recorded for R19)

- **One action-call format** `{thought, module, action, args}` (R14) replaces
  Python's two formats and its heal/alias layer (`code_agent.py:41-113`, H9). A
  GBNF grammar makes the heal layer unnecessary; under the Ollama scaffold (M2)
  the backend uses a JSON-schema `format`.
- **Error codes, not string matching.** `ActionResult.error_code` is empty
  exactly when `success` (M1, D13), so the loop never does `"OS BLOCK" in summary`
  (`run_state.py:292`) or `startswith("...")` checks.
- **Scratchpad is strict schema memory** (R7); session fields that are not LLM
  memory move to a separate **run record** (D12). Python's `run_state.json` is
  not imported.
- **Completion is an action** (`OrchestratorModule.complete_recipe`) gated by the
  recipe's validation hook, replacing Python's free `final_report` channel.

### Dependencies and non-goals

- Depends on M1 types (`Message`, `ActionCall`, `ActionResult`, `ToolInteraction`,
  `AgentScratchpad`, `RecipeCartridge`, `ValidationHook`), M2 `IInferenceBackend`
  + `OllamaHttpBackend`, and M3 `IAgentModule` + `ModuleRegistry` +
  `WorkspaceModule` + `ExecutionModule`.
- **Non-goals (deferred):** real KV checkpoint/rollback and GBNF (M5,
  `LlamaCppBackend`); KnowledgeModule (M6); other domain modules and script/plugin
  modules (M7); GUI and remote surfaces (M8-M10). M4 runs on the Ollama scaffold,
  where KV ops degrade to resending the full prompt (M2).

---

## Glossary

- **AgentLoop:** the single-threaded, deterministic driver that runs model turns
  until a recipe's exit gate is satisfied or the turn limit is hit (R2).
- **ContextCondenser:** owns the three-segment prompt (pinned prefix / anchored
  block / rolling tail) and the wipe policy (R6).
- **Pinned prefix:** segment `[0..P]`, system prompt + active recipe schema, never
  evicted.
- **Anchored block:** segment `[P+1..S]`, `AgentScratchpad` + module snapshots,
  evicted only on a wipe.
- **Rolling tail:** segment `[S+1..end]`, the last K `ToolInteraction` results,
  K = tier `rolling_tools`.
- **Wipe / condense:** clearing the rolling tail and refreshing the anchored block
  from current scratchpad + snapshots; the pinned prefix is untouched.
- **OrchestratorModule:** meta-module exposing `checkpoint_notes`,
  `trigger_context_condense`, `complete_recipe` (R11).
- **Run record:** loop-owned session metadata (`task_id`, `mode`, `instance_id`,
  `step_index`, `ground_truth`, last interaction); separate from scratchpad (D12).
- **Validation hook:** a recipe's `post_llm_validation_hook`; a deterministic
  module call that gates recipe completion (R12).
- **RuntimeTierConfig:** CPU-first config mapping a `ComputeProfile` to limits
  (condense threshold, rolling tools, output chars, thought tokens, gpu layers)
  (R16).
- **Tier:** a `ComputeProfile` (`cpu_low_spec_edge`, `cpu_moe_fast`,
  `gpu_high_vram`) selecting a set of limits.
- **Parity oracle:** the pinned Python source (`759212a`) whose behavior a C++
  piece is checked against (R5/R19).
- **Replayed backend:** a scripted `IInferenceBackend` used in unit tests so loop
  logic runs deterministically without a network (R4/Req 8).

---
## Requirements

### Requirement 1: Single-threaded deterministic AgentLoop

**User Story:** As the orchestrator of the agent, I want one simple deterministic
loop that drives the LLM through module actions, so that behavior is predictable,
debuggable, and matches Python's "one dumb loop" (R2, `code_agent.py`).

#### Acceptance Criteria

1. WHEN the loop starts THEN it SHALL run on a single thread with no async or
   coroutines, with all turn state owned by the `AgentLoop` frame or the
   `ContextCondenser` (R2).
2. WHEN a turn begins THEN the loop SHALL build the prompt from the condenser,
   call `IInferenceBackend::generate` with an `OutputConstraint` for the action
   schema, parse the reply into an `ActionCall`, dispatch exactly one module
   action, and record the result as a `ToolInteraction` (parity:
   `code_agent.py` one-tool-per-turn, `tools[0]` only at `:342`).
3. WHEN the model reply fails to parse as a valid `ActionCall` THEN the loop
   SHALL NOT throw; it SHALL record a parse failure, append a corrective user
   message, and continue to the next turn (parity: `code_agent.py:308-326`).
4. WHEN a dispatched action targets an unknown module, an action not exposed by
   the recipe, or an action that returns a failed `ActionResult` THEN the loop
   SHALL surface the `error_code` to the next turn WITHOUT inspecting
   `llm_facing_output` text to classify the outcome (R19; contrast
   `run_state.py:292`).
5. WHEN the turn count reaches the tier's configured maximum THEN the loop SHALL
   stop and return a terminal result flagged as "turn limit reached", not as
   success (parity: `code_agent.py` `_max_turns` and the `for...else` limit
   branch).
6. WHEN the same inputs (recipe, user request, a recorded/replayed backend) are
   run twice THEN the loop SHALL produce byte-identical turn transcripts
   (determinism, R2).

### Requirement 2: ContextCondenser with three KV segments

**User Story:** As the agent's memory manager, I want context organized into the
three segments the design mandates, so that the system prompt and recipe schema
are never evicted, scratchpad and module snapshots survive until a wipe, and only
the recent tail rolls (R6).

#### Acceptance Criteria

1. WHEN the condenser builds a prompt THEN it SHALL emit segments in this order:
   (a) pinned prefix = system prompt + active recipe schema; (b) anchored block =
   `AgentScratchpad` + module state snapshots; (c) rolling tail = the last K
   `ToolInteraction` results, where K is the tier's `rolling_tools` (R6, R16).
2. WHEN a `ToolInteraction` is recorded AND the rolling tail already holds K
   entries THEN the oldest tail entry SHALL be dropped before the new one is
   added (parity: `_keep_recent_turns`, `context_manager.py:83-95`; the design
   doc's `record_tool_cycle` ring buffer, D:L130-141).
3. WHEN a single action result exceeds the tier's `tool_output_chars` THEN the
   condenser SHALL store a head+tail-truncated view in the rolling tail and spill
   the full text to a side buffer reachable by reference (R8; contrast Python's
   head-only `truncate_text`, `code_context.py`).
4. WHEN a context wipe is triggered THEN the pinned prefix SHALL be unchanged, the
   anchored block SHALL be refreshed from the current scratchpad and module
   snapshots, and the rolling tail SHALL be cleared (R6; parity: Python clears
   history on step advance, `context_manager.py` `on_step_advance`).
5. WHEN estimating token footprint THEN the condenser SHALL use the `ceil(chars/4)`
   heuristic already in `estimate_tokens` (M3) and SHALL agree with
   `estimate_messages_tokens` (`context_manager.py:18-28`) within rounding on a
   set of fixture message lists.
6. WHEN the estimated footprint of the assembled prompt reaches the tier's
   `condense_threshold` THEN the condenser SHALL report that a wipe is due
   (parity: `should_force_summarize`, `context_manager.py`).

### Requirement 3: OrchestratorModule

**User Story:** As the agent, I want a meta-module that owns the scratchpad,
checklist, and completion gate, so that progress notes and recipe completion are
first-class actions the LLM invokes (R11).

#### Acceptance Criteria

1. WHEN OrchestratorModule is registered THEN it SHALL expose the actions
   `checkpoint_notes`, `trigger_context_condense`, and `complete_recipe` via
   `get_actions()` with JSON-schema parameters (R11, R10).
2. WHEN `checkpoint_notes` is called THEN it SHALL update the `AgentScratchpad`
   (current_hypothesis, verified_facts, failed_approaches_do_not_repeat,
   next_immediate_action, checklist) and SHALL reject the call with a failed
   `ActionResult` IF a field required by the active recipe is missing or empty
   (R11: "validates required scratchpad fields before a wipe"; contrast Python,
   which does not validate, `run_state.py`).
3. WHEN `trigger_context_condense` is called THEN the module SHALL request a wipe
   from the condenser AFTER confirming the scratchpad passes validation, so the
   agent cannot lose history before its notes are saved (R11).
4. WHEN `complete_recipe` is called AND the recipe has a `post_llm_validation_hook`
   with `must_succeed = true` THEN completion SHALL be refused until the hook
   passes (see Requirement 5); WHEN there is no hook THEN `complete_recipe`
   SHALL complete immediately.
5. WHEN `export_state_snapshot` then `restore_state_snapshot` is applied THEN the
   scratchpad and checklist SHALL round-trip byte-equal (R10; parity with the M3
   snapshot contract).

### Requirement 4: RuntimeTierConfig (CPU-first)

**User Story:** As a user on varied hardware, I want one code path whose limits
scale by compute tier, so that the agent runs on a CPU edge box and a GPU box
without separate builds (R16).

#### Acceptance Criteria

1. WHEN a `ComputeProfile` is selected THEN `RuntimeTierConfig` SHALL provide:
   `condense_threshold` (2048 CPU-low / 6144 GPU), `rolling_tools` (2 / 4),
   `tool_output_chars` (1500 / 4500), `max_thought_tokens` (45 / 150), and
   `gpu_layers` (0 / 999) (R16, D:L706-734).
2. WHEN the config is CPU-first THEN the default profile SHALL be a CPU tier and
   the GPU tier SHALL be an explicit boost, not the default (R16: "console-first").
3. WHEN universal flags (KV rollback, GBNF, n-gram) are read THEN they SHALL be
   present in the config regardless of tier, with the Ollama scaffold reporting
   KV rollback and GBNF as unsupported (M2 `supports_kv_reuse`), so M5 can enable
   them without a config change.
4. WHEN the loop and condenser read limits THEN they SHALL take them from
   `RuntimeTierConfig` only, with no hardcoded thresholds in loop or condenser
   code (R16; contrast Python keying tiers on `num_ctx`, `context_budget.py`).

### Requirement 5: Recipe validation hook as a loop exit gate

**User Story:** As the recipe author, I want the loop to refuse to finish while a
recipe's validation hook fails, so that "done" is proven by a deterministic check,
not asserted by the model (R12).

#### Acceptance Criteria

1. WHEN a recipe defines `post_llm_validation_hook{module, action, must_succeed,
   on_failure_instruction}` THEN the loop SHALL run that hook as a deterministic
   module call (not an LLM turn) whenever `complete_recipe` is attempted (R12).
2. WHEN `must_succeed = true` AND the hook returns a failed `ActionResult` THEN
   the loop SHALL NOT exit; it SHALL inject `on_failure_instruction` as the next
   turn's guidance and continue (R12: "the loop cannot exit while the hook
   fails").
3. WHEN the hook returns a successful `ActionResult` THEN the loop SHALL exit with
   a terminal result flagged as success and SHALL include the completion output.
4. WHEN a hook names a module not in the recipe's `load_modules`, or an action
   that module does not expose for hooks THEN recipe validation SHALL fail at load
   time with a `SchemaError` naming the JSON path (consistent with M3
   `ModuleRegistry::validate_recipe`).
5. WHEN the hook is invoked THEN its deterministic call SHALL be allowed to target
   actions outside `expose_actions` (a `HookCall` is made by the runner, not the
   LLM; M1 `recipe.hpp`).

### Requirement 6: Run record for non-memory session fields

**User Story:** As the loop, I want session bookkeeping kept separately from the
LLM's self-notes, so that scratchpad memory stays a clean strict schema and
session metadata is owned by the loop (D12, section 8.1).

#### Acceptance Criteria

1. WHEN a run starts THEN the loop SHALL create a run record holding `task_id`,
   `mode`, `instance_id`, `step_index`, `ground_truth`, and the last
   `ToolInteraction` (D12; fields drawn from `TaskRunContext`,
   `run_state.py:95-220`).
2. WHEN session fields change (a new step, a new interaction, updated ground
   truth) THEN the loop SHALL update the run record, and these fields SHALL NOT
   appear in `AgentScratchpad` (separation of concerns, R7 + D12).
3. WHEN Python per-task `run_state.json` files are present THEN M4 SHALL NOT import
   them; a C++ run starts fresh (D12).
4. IF the run record is serialized THEN it SHALL round-trip byte-equal through the
   canonical JSON serializer (consistency with M1).

### Requirement 7: Code recipe cartridge and `code_smoke_file` parity

**User Story:** As a reviewer who never accepts "done" without proof, I want the
canonical harness scenario to pass end-to-end on the C++ loop, so that M4 is
proven against the same acceptance Python uses.

#### Acceptance Criteria

1. WHEN M4 ships THEN it SHALL include one code recipe cartridge that loads
   `WorkspaceModule` and `ExecutionModule`, exposes the actions needed to create
   and write a file, and defines a `post_llm_validation_hook` (R12).
2. WHEN the `code_smoke_file` scenario runs THEN the loop SHALL drive the agent to
   create `harness_smoke.py` containing `HARNESS_OK`, and acceptance SHALL be
   judged by the Python rubric: a file matching `**/harness_smoke.py` exists and
   contains `HARNESS_OK` (`capability_harness.py` `code_smoke_file`).
3. WHEN the scenario is run 3 times THEN it SHALL pass 3/3 (the Python baseline is
   3/3, `docs/reliability-plan/phase-0-baseline-and-gates.md`).
4. WHEN the validation hook is forced to fail (a fault-injection build where the
   written file omits `HARNESS_OK`) THEN the loop SHALL NOT report success; it
   SHALL continue until the turn limit and return a non-success terminal result
   (Requirement 5; the M4 proof-of-done "forced-failure test").
5. WHEN the scenario path interacts with the filesystem THEN every write SHALL
   stay inside the workspace root via the M3 `PathFirewall`.

### Requirement 8: Verification, proof, and R20 accounting

**User Story:** As a reviewer, I want each M4 claim backed by a repeatable check on
every build lane, so that correctness is demonstrated, not summarized.

#### Acceptance Criteria

1. WHEN M4 is verified THEN unit tests SHALL cover: the loop turn cycle (Req 1),
   the three-segment condenser and eviction/spill (Req 2), OrchestratorModule
   actions and scratchpad validation (Req 3), tier limits (Req 4), the exit-gate
   refusal and success paths (Req 5), the run record round-trip (Req 6), and the
   recipe cartridge load/validation (Req 7).
2. WHEN condenser and token-estimate behavior is tested THEN results SHALL be
   compared against Python oracle fixtures generated from the pinned checkout
   (`estimate_messages_tokens`, `_keep_recent_turns`), regenerable by the fixture
   generator with `git status` left clean (parity method established in 8.1-8.3).
3. WHEN the loop is tested without a live server THEN a scripted/replayed backend
   SHALL stand in for `IInferenceBackend`, so loop logic is deterministic and
   CI-safe (no network in CI).
4. WHEN the `code_smoke_file` 3/3 run and the forced-failure run are executed THEN
   they SHALL run as live tests against the stock Ollama server (not in CI, same
   policy as M2 live tests) and the evidence (turn count, acceptance result)
   SHALL be recorded.
5. WHEN M4 completes THEN all five build lanes (`msvc-release`, `msvc-asan`,
   `msvc-release-cuda`, `mingw-san`, `linux-san`) and CI (3 jobs) SHALL pass on a
   fresh clone, with ASan/UBSan/LSan reporting nothing.
6. WHEN M4 completes THEN RECON_MAP SHALL record the M4 result with a section
   (8.4) of per-feature verdicts against Python, and the R20 line count (C++ LOC
   added vs the Python LOC it replaces: `code_agent.py` loop ~230,
   `context_manager.py` ~260, `run_state.py` session portion, `context_budget.py`
   tiers). IF C++ is not smaller THEN the M4 row SHALL say why.

---

## Traceability

| Requirement | Governing | Python oracle |
|---|---|---|
| 1 AgentLoop | R2, R14, R19 | `code_agent.py` `run_tool_session` |
| 2 ContextCondenser | R6, R8, R16 | `context_manager.py` |
| 3 OrchestratorModule | R7, R10, R11 | `run_state.py`, `agent_tools.py` |
| 4 RuntimeTierConfig | R16 | `context_budget.py` |
| 5 Exit gate | R12 | `harness_gate.py`, `ModuleRegistry::validate_recipe` (M3) |
| 6 Run record | D12, R7 | `run_state.py` `TaskRunContext` |
| 7 Code cartridge | R12, R5 | `capability_harness.py` `code_smoke_file` |
| 8 Proof | R19, R20, R4 | fixture-generator parity method (8.1-8.3) |


