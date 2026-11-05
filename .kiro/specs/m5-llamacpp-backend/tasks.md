# Implementation Plan: M5 — LlamaCppBackend (direct KV-aware inference, GBNF)

## Overview

M5 adds `LlamaCppBackend`, a second `IInferenceBackend` linked directly against
upstream llama.cpp. It makes the M2 KV interface real (`mark_checkpoint` /
`rollback_to` -> `llama_memory_seq_rm`, R6) and enforces the action-call schema with
GBNF (`json_schema_to_grammar` -> `llama_sampler_init_grammar`, R14). The Ollama
backend (M2) stays as the parity cross-check.

The plan builds in dependency order: the pinned llama.cpp dependency + the Qwen 3.5
load check and the cross-lane `AQUILA_LLAMACPP` strategy first (everything else needs
them), then the RAII wrappers + `LlamaSession` (model/context/KV), the
`GrammarFactory` (schema -> GBNF), the `LlamaCppBackend` (append / checkpoint /
rollback / generate with the sampler chain), then the full verification: the 8
correctness properties as RapidCheck tests over a small-model CPU session, the
deterministic lifecycle/error tests, the opt-in GPU/live proofs (N-trials GBNF
validity, post-wipe prefill savings), the Ollama parity cross-check, all five lanes +
CI, and the RECON_MAP 8.5 / R20 accounting.

New headers land under `src/core/include/aquila/inference/`, sources under
`src/core/inference/`, compiled into `aquila_core` behind the `AQUILA_LLAMACPP` option
so sanitizer/cross-compiler lanes stay green. Unit tests go in `tests/unit/`
(Catch2WithMain, small/vocab-only GGUF, CI-safe); GPU/full-model tests go in
`tests/live/` (opt-in `-DAQUILA_LIVE_TESTS=ON`, excluded from CI). Property tests use
RapidCheck's Catch2 integration (added in M4), run >= 100 iterations, are tagged
`// Feature: m5-llamacpp-backend, Property {N}: {property_text}`, and run over a CPU
session with a small model (or at the pure-function level) so they stay deterministic.

## Tasks

- [x] 1. Pin upstream llama.cpp, add the cross-lane build strategy, and verify Qwen 3.5 loads
  - Create `cmake/AquilaLlamaCpp.cmake` fetching upstream `ggml-org/llama.cpp` pinned by URL + SHA256 (compute the hash from the archive, as prior deps did); include it from the top-level `CMakeLists.txt` after the other `Aquila*.cmake` modules
  - Add the `AQUILA_LLAMACPP` build option (default ON) and the per-lane profile from the design's lane table: CUDA on MSVC (cl+nvcc, sm_89, H12); CPU-only with llama.cpp's own targets built WITHOUT Aquila's sanitizer/warning flags on `linux-san`; OFF (stubbed) on `mingw-san` and `msvc-asan`
  - Define `AQUILA_HAS_LLAMACPP` so TUs can guard llama.cpp includes; ensure every lane still configures + builds
  - Spike (Req 1.4, D4): build the pinned upstream and attempt to load `F:\Users\myfri\agent-projects\Qwen3.5-9B-Q4_K_M.gguf`; record in the task report whether it loads unpatched or needs the fork's Qwen 3.5 patches, and the resolution if patches are needed
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 7.1, 7.2_

- [x] 2. Implement RAII handle wrappers and `LlamaSession`
  - [x] 2.1 Implement the RAII wrappers and session construction
    - Create `src/core/include/aquila/inference/llama_session.hpp` with `ModelPtr`/`ContextPtr`/`SamplerPtr` (`unique_ptr` + deleters calling `llama_model_free`/`llama_free`/`llama_sampler_free`), a `LlamaBatch` owning wrapper, and the `LlamaSession` class; a process-lifetime `llama_backend_init`/`llama_backend_free` guard
    - Create `src/core/inference/llama_session.cpp`: load the model (`llama_model_load_from_file`), create the context (`llama_init_from_model`) honoring `n_ctx` and `n_gpu_layers` from `LlamaConfig`; throw a typed error on load failure (Req 2.2)
    - Add `inference/llama_session.cpp` to `aquila_core` in `src/core/CMakeLists.txt` under the `AQUILA_LLAMACPP` guard; link the llama.cpp target
    - _Requirements: 2.1, 2.2, 2.3, 1.1_

  - [x] 2.2 Implement tokenize/decode, position, and rollback
    - Implement `decode_text` (role-framed tokenize via `llama_tokenize`/`llama_chat_apply_template` + `llama_decode`), advancing `pos_`; `context_overflow` when the position would exceed `n_ctx` (Req 2.4)
    - Implement `position()` (mirrors `llama_memory_seq_pos_max(mem,0)+1`), `rollback_to(pos)` (`llama_memory_seq_rm(mem,0,pos,-1)`; throw `std::out_of_range` when `pos > position()`), and a `prefill_tokens` counter for Req 5
    - Implement `decode_one`, `vocab()`, `ctx()`, `n_ctx()`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 2.4, 5.1_

  - [x]* 2.3 Write property tests for checkpoint/rollback over a small-model session
    - Create `tests/unit/llama_session_test.cpp` (guarded by `AQUILA_HAS_LLAMACPP`, added to `tests/unit/CMakeLists.txt`), using a small/vocab-only GGUF
    - **Property 1: Rollback is exact** — after `rollback_to(checkpoint)` the position equals the checkpoint and a subsequent deterministic generate equals the no-extra-tokens generate. **Validates: Requirements 3.5**
    - **Property 2: Rollback past end throws** — `rollback_to(pos > end)` throws `std::out_of_range`, session unchanged. **Validates: Requirements 3.4**
    - **Property 3: Checkpoint equals decoded token count** — `mark_checkpoint()` tracks the decoded count / `llama_memory_seq_pos_max`. **Validates: Requirements 3.2**
    - _Requirements: 3.2, 3.4, 3.5_

  - [x]* 2.4 Write the RAII / no-leak lifecycle and context-overflow unit tests
    - In `llama_session_test.cpp`: construct+destroy a session on a small model with LSan/CRT clean (Req 2.3); a prompt exceeding a tiny `n_ctx` yields `context_overflow` (Req 2.4)
    - _Requirements: 2.3, 2.4_

- [x] 3. Implement the `GrammarFactory` (schema -> GBNF)
  - [x] 3.1 Implement `gbnf_for` and `make_grammar_sampler`
    - Create `src/core/include/aquila/inference/grammar.hpp` and `src/core/inference/grammar.cpp` (added to `aquila_core` under the guard)
    - `gbnf_for(OutputConstraint)`: `json_schema` -> `json_schema_to_grammar(schema)` (llama.cpp `common/`); `json` -> a generic-JSON grammar; `none` -> `nullopt`. Cache by the schema's canonical string
    - `make_grammar_sampler(vocab, gbnf)`: `llama_sampler_init_grammar`; return a null `SamplerPtr` (for the caller to map to `invalid_request`) when the grammar is NULL
    - _Requirements: 4.1, 4.2, 4.3_

  - [x]* 3.2 Write unit tests for the grammar factory
    - Create `tests/unit/grammar_test.cpp` (guarded, added to CMake): the action-call schema maps to a non-empty GBNF; `none` -> `nullopt`; a malformed schema/grammar yields a null sampler (not a crash)
    - **Property 5: Grammar failure is typed, not fatal** — a malformed grammar never crashes and produces no sampler. **Validates: Requirements 4.3**
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. Implement `LlamaCppBackend`
  - [x] 4.1 Implement construction, `append`, `mark_checkpoint`, `rollback_to`, and profile
    - Create `src/core/include/aquila/inference/llama_backend.hpp` (`LlamaConfig`, `LlamaCppBackend`) and `src/core/inference/llama_backend.cpp` (added to `aquila_core` under the guard)
    - Ctor builds a `LlamaSession` from `LlamaConfig` (derive `n_gpu_layers` 0/999 and `n_ctx` from the tier); `append` -> `decode_text`; `mark_checkpoint` -> `position()`; `rollback_to` -> `session.rollback_to`; `active_profile()`; `supports_kv_reuse() == true`
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 6.5_

  - [x] 4.2 Implement `generate` with the sampler chain and streaming
    - `build_sampler(params)`: `penalties` -> `top_k`/`top_p` (if set) -> `temp` -> grammar sampler (when a constraint is set; `invalid_request` on NULL grammar) -> `dist(seed)` or `greedy` at temperature 0 (deterministic, Req 4.5)
    - Token loop: sample -> `decode_one` -> `llama_token_to_piece` -> stream via `on_token` (false -> `cancelled`) -> stop on EOS (`llama_vocab_is_eog`, `done_reason="stop"`) or `max_tokens` (`"length"`); no-progress `timeout_s` -> `stream_stalled`; `llama_decode` nonzero -> `decode_failed`
    - On return, roll the KV back to the pre-call checkpoint so `generate` leaves the context unchanged (Req 6.4); populate `prompt_tokens`/`completion_tokens`/`done_reason`
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2, 6.3, 6.4_

  - [x]* 4.3 Write property tests for generate, grammar validity, cancellation, and prefix reuse
    - Create `tests/unit/llama_backend_test.cpp` (guarded, added to CMake), small-model CPU session
    - **Property 4: GBNF output always parses** — schema-constrained generate yields `parse<ActionCall>`-valid content. **Validates: Requirements 4.4**
    - **Property 6: generate() leaves KV unchanged** — checkpoint before/after equal; repeat generate identical. **Validates: Requirements 6.4**
    - **Property 7: Cancellation stops promptly and is typed** — cancel-after-k -> `cancelled`, KV unchanged. **Validates: Requirements 6.1**
    - **Property 8: Prefix reuse decodes fewer tokens** — post-wipe `prefill_tokens` < full-prompt prefill. **Validates: Requirements 5.1, 5.2**
    - _Requirements: 4.4, 5.1, 5.2, 6.1, 6.4_

  - [x]* 4.4 Write the streaming/EOS/error-vocabulary unit tests
    - In `llama_backend_test.cpp`: callback receives tokens in order; EOS -> `done_reason="stop"`, `max_tokens` -> `"length"`; `context_overflow`/`decode_failed`/`invalid_request` are typed `GenerationResult` errors, never model content
    - _Requirements: 6.1, 6.2, 4.3_

- [x] 5. Checkpoint - Ensure all tests pass for the session, grammar, and backend
  - Ensure all tests pass on the lanes that build the backend; ask the user if questions arise.

- [ ] 6. Add the Ollama parity cross-check
  - [ ]* 6.1 Implement the backend parity test
    - Add a test (guarded; live where both backends need the model) comparing `LlamaCppBackend` and `OllamaHttpBackend` on the same prompt + action-call schema: both yield schema-valid `ActionCall`s and both are deterministic at a fixed seed; record any tokenizer/template/sampler divergence as an explained finding (R19)
    - _Requirements: 8.4_

- [ ] 7. Add the opt-in GPU/live proofs (excluded from CI)
  - [ ] 7.1 Implement the live proofs: GBNF validity (PASS) and the honest KV/M-RoPE finding
    - `tests/live/llama_backend_live_test.cpp` (`tests/live/CMakeLists.txt`, `-DAQUILA_LIVE_TESTS=ON`, excluded from CI) against `Qwen3.5-9B-Q4_K_M.gguf` on the RTX 4070
    - **Proof 1 (GBNF validity) — PASSED:** N >= 50 schema-constrained generations, every output `parse<ActionCall>`-valid (0 invalid). Recorded: 60 trials, 54 EOS-completed, 54/54 valid, 0 invalid. Keep as the "invalid JSON impossible in N trials" proof-of-done
    - **Proof 2 (prefix reuse) — REFRAME to the finding:** assert that a mid-sequence `rollback_to(P)` on Qwen 3.5 surfaces the M-RoPE inconsistent-position condition as a typed `GenerationResult` failure (NOT a crash), and that a full reset (`rollback_to(0)`) + re-decode succeeds. Do NOT assert an unsupported partial-rollback token saving on Qwen 3.5; point the measured prefix-reuse savings claim at the CPU Property 8 (plain-RoPE small model), recording both the CPU numbers and the Qwen 3.5 typed-failure
    - Record the finding verbatim (the inconsistent-position error text, recurrent/M-RoPE cause) so RECON_MAP task 9.2 and the Req 9 bake-off cite it
    - _Requirements: 4.4, 5.1, 5.2, 3.6, 8.3_

- [ ] 8. Checkpoint - Ensure all tests pass for parity and the live proofs
  - Ensure the unit suite is green on building lanes and the live proofs pass on the GPU host; ask the user if questions arise.

- [ ] 9. Verify all five lanes, sanitizers, and the cross-lane stub strategy
  - [ ] 9.1 Verify build lanes and sanitizers clean on a fresh clone
    - On a fresh clone: build+test the four local lanes (`msvc-release`, `msvc-asan`, `msvc-release-cuda`, `mingw-san`) and confirm the three CI jobs (incl. `linux-san`) pass; confirm `linux-san` builds `LlamaCppBackend` CPU-only and its unit tests are ASan/UBSan/LSan clean, and that `msvc-asan`/`mingw-san` stub the backend and skip its tests without failing to compile
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1_

  - [ ] 9.2 Record RECON_MAP section 8.5, flags, R20, and the S7/Qwen findings
    - Add RECON_MAP 8.5 (per-feature verdicts vs Python's `OllamaClient` and the R15 interface); record `UniversalFlags.kv_rollback`/`gbnf` flipped true for this backend and the R17 CPU-engine items deferred; record the upstream-vs-fork Qwen 3.5 load finding (task 1) and resolution; confirm the S7 KV API note against the upstream header actually built; add llama.cpp to the dependencies table and the R20 line-count accounting (additive native backend; downstream parser/heal condensation credited when retired)
    - _Requirements: 8.5, 8.6, 1.4, 7.3_

- [ ] 11. Context-strategy bake-off (decide D14 / resolve the M-RoPE finding)
  - [ ] 11.1 Pin the Qwen 3.5 4B model and define the `ContextStrategy` interface
    - Add `Qwen3.5-4B-Q4_K_M.gguf` pinned by URL + SHA256 (compute the hash from the archive as the 9B/tiny models were pinned); wire it for the opt-in live/bake-off lane like `AQUILA_TINY_GGUF`
    - Create `src/core/include/aquila/context/context_strategy.hpp`: the kept `ContextStrategy` interface (`set_prefix`/`add_turn`/`next_action`/`stats`/`name`) + `StrategyStats` (tokens decoded, compactions, resets), compiled into `aquila_core` behind `AQUILA_LLAMACPP`
    - _Requirements: 9.1, 9.4_
  - [ ] 11.2 Implement the three strategies behind the interface
    - `KvRollbackStrategy` (control): pin prefix, append turns, mid-sequence `rollback_to` wipe; surface the Qwen 3.5 M-RoPE condition as a typed failure (Req 3.6), valid on plain-RoPE
    - `EoCCStrategy`: grow to a 16K threshold, then condense the message list + rebuild, relying on llama.cpp auto prefix-cache (full reset, no partial rollback)
    - `SacStrategy`: fresh context per action fed an aggressively summarized state each turn
    - Sources under `src/core/context/*.cpp`, added to `aquila_core` under the guard; all reuse the M5 `LlamaCppBackend` unchanged (Req 9.7)
    - _Requirements: 9.1, 9.7_
  - [ ] 11.3 Build the task suite and the scoring harness with the decision rule
    - `tests/live/bakeoff_tasks.hpp`: 5-10 multi-turn tool-use scenarios that force long context (a fact set early must be recalled after many intervening tool calls) + a deterministic oracle per task
    - `tests/live/context_bakeoff_live_test.cpp` (`-DAQUILA_LIVE_TESTS=ON`, out of CI): run each strategy over the suite, record per task completion/tokens/latency/outcome-class/fidelity to a results artifact (JSON under a results dir)
    - Encode the decision rule in the harness so the winner is computed, not eyeballed: crash disqualifies; max completion rate wins; ties broken by fewest tokens then lowest latency
    - _Requirements: 9.2, 9.3, 9.5_
  - [ ] 11.4 Run the bake-off and record the decision
    - Run on **Qwen 3.5 4B Q4_K_M (CPU)** — the deciding lane; apply the rule to pick the winner
    - Run on **Qwen 3.5 9B Q4_K_M (GPU, RTX 4070)** as a non-gating confirmation lane when the GPU is free; record whether it agrees
    - Record in RECON_MAP: the winning strategy, the measured numbers behind the decision, the disqualified/rejected strategies with why, the M-RoPE finding resolution, and the explicit hand-off (the winning `ContextStrategy` is M6's ContextCondenser starting point). Flag the open-model verbosity-collapse risk (paper Appendix D) for M6 tuning
    - _Requirements: 9.4, 9.5, 9.6_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass; ask the user if questions arise.

## Notes

- Tasks marked `*` are optional test sub-tasks (property, unit, parity) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references the specific requirement clauses it implements for traceability.
- Property-based tests use RapidCheck's Catch2 integration (added in M4), run >= 100 iterations, are tagged `// Feature: m5-llamacpp-backend, Property {N}: {property_text}`, and run over a small-model CPU session (or pure-function level) so CI stays deterministic.
- All 8 correctness properties map to tasks: P1-P3 (session: task 2.3), P4/P6/P7/P8 (backend: task 4.3), P5 (grammar: task 3.2). The N-trials (P4) and measured prefix-reuse (P8) forms also run as the opt-in live proofs (task 7.1).
- Build reality (H12): CUDA needs the MSVC host compiler, so the GPU path is MSVC-only; sanitizer lanes build the backend CPU-only (`linux-san`) or stub it (`mingw-san`, `msvc-asan`) behind `AQUILA_LLAMACPP`. No lane is left broken.
- Live/GPU tests (full model, RTX 4070) are excluded from CI, matching the M2/M4 live-test policy; their CI-safe counterparts are the small-model property tests.
- GPU finding (M5): Qwen 3.5 (recurrent/M-RoPE) cannot do mid-sequence KV rollback; the original Proof 2 was reframed (task 7.1) to record this as a typed failure, and task group 11 runs the Req 9 bake-off to decide the replacement context-management strategy (D14) empirically rather than by assumption.
- Task 11 (bake-off) reuses the M5 `LlamaCppBackend` unchanged and runs opt-in in `tests/live/` like the other live proofs; the `ContextStrategy` interface + 3 strategies are kept code under `src/core/context/` so the winner seeds M6. 4B Q4_K_M (CPU) decides; 9B (GPU) confirms, non-gating.
- Checkpoints ensure incremental validation at reasonable breaks.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.2", "4.1"] },
    { "id": 4, "tasks": ["4.2"] },
    { "id": 5, "tasks": ["4.3", "4.4"] },
    { "id": 6, "tasks": ["5", "6.1", "11.1"] },
    { "id": 7, "tasks": ["7.1", "11.2"] },
    { "id": 8, "tasks": ["8", "9.1", "11.3"] },
    { "id": 9, "tasks": ["9.2", "11.4"] },
    { "id": 10, "tasks": ["10"] }
  ]
}
```
