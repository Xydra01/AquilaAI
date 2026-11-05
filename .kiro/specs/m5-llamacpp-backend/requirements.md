# Requirements Document

**Spec:** M5 — LlamaCppBackend (direct KV-aware inference, GBNF)

## Introduction

M5 replaces the Ollama HTTP scaffold (M2) with a backend linked directly against
the llama.cpp C API, satisfying R15's "linked directly against the C/C++ inference
API (not HTTP per turn)" for the first time. It is the milestone that makes the
KV-cache prefix pinning (R6) and grammar-constrained generation (R14) real: the
`IInferenceBackend` KV ops (`mark_checkpoint` / `rollback_to`), which the Ollama
backend degraded to resending the full prompt, now map onto llama.cpp's sequence
memory, and the action-call JSON schema is enforced by a GBNF grammar instead of
Ollama's `format` field.

Scope, from the M5 row of `docs/recon/RECON_MAP.md` section 8:

> `LlamaCppBackend` (upstream): KV checkpoint/rollback (`llama_memory_seq_rm`),
> GBNF for the R14 action call.

Proof of done, from the same row:

> Post-wipe prefill token count measured < full prompt; invalid JSON impossible in
> N trials.

### Governing principles (RECON_MAP section 2.1)

- **R1** Strict C++20, zero raw owning pointers; RAII wrappers around every
  llama.cpp handle (`llama_model`, `llama_context`, `llama_sampler`, `llama_batch`).
- **R2** Single-threaded, deterministic core. llama.cpp's own compute threads are
  internal to the backend (the remaining parallelism S1 allows, via R17).
- **R6** Three KV segments: the pinned prefix `[0..P]` is never evicted; a wipe
  removes only `[P+1..end]`. M5 makes this a real `llama_memory_seq_rm` instead of
  a full-context resend.
- **R14** The action call is grammar-enforced JSON `{thought, module, action,
  args}`; M5 compiles its JSON schema to GBNF.
- **R15** `IInferenceBackend`, KV-aware, linked against the C/C++ inference API:
  `append_to_kv_cache`, `mark_kv_checkpoint`, `rollback_kv_to`,
  `generate_structured(gbnf, max_tokens, ngram)`, `ComputeProfile`.
- **R16** CPU-first `RuntimeTierConfig`; `gpu_layers` (0 / 999) is already a tier
  knob (M4). M5 honors it when creating the context.
- **R18** Model: Qwen 3.5 family. A standalone `Qwen3.5-9B-Q4_K_M.gguf` (5.47 GB)
  exists at `F:\Users\myfri\agent-projects\` for the live/GPU path.
- **R19** Improve, don't transliterate. Diverge from Python only to fix a concrete
  problem, cited by file:line.
- **R20** Condense. C++ LOC measured against the Python it replaces.

### The interface M5 must now honor for real (M2, `inference/backend.hpp`)

`IInferenceBackend` was designed KV-aware from day one (M2):

- `void append(const Message&)` — add a message to the context.
- `std::size_t mark_checkpoint() const` — a position in the context.
- `void rollback_to(std::size_t checkpoint)` — truncate to a checkpoint; throws
  `std::out_of_range` past the end.
- `GenerationResult generate(const GenerationParams&, const TokenCallback&)` —
  reply to the current context; the context is left unchanged.
- `ComputeProfile active_profile()`, `bool supports_kv_reuse()`.

Shared value types (M2) are reused unchanged: `GenerationParams{temperature,
max_tokens, num_ctx, repeat_penalty, repeat_last_n, seed, think, keep_alive,
constraint, timeout_s}`, `GenerationResult{ok, error_code, error_detail, content,
thinking, done_reason, prompt_tokens, completion_tokens}`, `OutputConstraint{none,
json, json_schema}`, `ComputeProfile{gpu_high_vram, cpu_moe_fast,
cpu_low_spec_edge}`, `TokenCallback`.

### The real llama.cpp API on this machine (verified against the header)

Confirmed against the pinned upstream header (`ggml-org/llama.cpp` tag b12116; the
turboquant fork was rejected per D4; S7 note re-verified against upstream during M5):

- **Memory / KV:** `llama_get_memory(ctx)`; `llama_memory_seq_rm(mem, seq_id, p0,
  p1)` where `p1 < 0` means `[p0, inf)` (remove everything after a position — this
  is prefix pinning); `llama_memory_seq_pos_max/min`; `llama_memory_clear`.
- **Decode:** `llama_decode(ctx, batch)`, `llama_batch_init/free`,
  `llama_batch_get_one`.
- **GBNF:** `llama_sampler_init_grammar(vocab, grammar_str, grammar_root)` — returns
  NULL if the grammar fails to parse.
- **Sampler chain:** `llama_sampler_chain_init/add`, `_init_temp`, `_init_top_k`,
  `_init_top_p`, `_init_penalties`, `_init_dist(seed)`, `_init_greedy`,
  `llama_sampler_sample(smpl, ctx, idx)`.
- **Schema → GBNF:** `json_schema_to_grammar(const common_json&, bool
  force_gbnf)` in llama.cpp's `common/` — NOT `nlohmann::ordered_json`; bridge our
  `Json` via `common_json::parse(json.dump())` (M5 implementation finding).

### Decisions settled for M5

- **D4 (source): upstream `ggml-org/llama.cpp`,** pinned by SHA via FetchContent
  (user, 2026-11-04). M5 first verifies whether stock upstream loads
  `Qwen3.5-9B-Q4_K_M.gguf` unpatched; if it needs the fork's Qwen 3.5 patches
  (`common/arg.cpp`, `src/llama-model-loader.cpp`, `src/llama-model.cpp`,
  `src/models/qwen35.cpp`), that is recorded as a finding and resolved then
  (cherry-pick upstream, or a documented fallback), not assumed.
- **CUDA requires the MSVC host compiler (H12).** The llama.cpp CUDA backend
  builds under cl.exe + nvcc, not llvm-mingw clang. M5's GPU path is an
  MSVC-lane concern; the sanitizer lanes (mingw-san / linux-san) build the
  backend CPU-only or stub it (see Requirement 7).
- **R17 CPU-engine discipline is mostly M5-deferred.** M5 requires only KV reuse +
  GBNF (the proof-of-done). Repacked quants, BLAS prefill tuning, P-core pinning,
  and n-gram prompt-lookup speculation are recorded as deferred; the backend is
  structured so they slot in later, and `UniversalFlags.ngram` already exists in
  the tier config (M4). M5 does flip `UniversalFlags.kv_rollback` and
  `UniversalFlags.gbnf` to true for the llama.cpp backend.

- **D14 (context-management strategy): DECIDED BY BAKE-OFF, not assumption.** The
  GPU proof surfaced that Qwen 3.5 (recurrent/M-RoPE) cannot do mid-sequence KV
  rollback (Requirement 3.6), which is the exact operation R6's KV-wipe condenser
  depended on. Rather than pick a replacement by argument, M5 runs a controlled
  bake-off (Requirement 9) of three context-management strategies on the real Qwen
  3.5 family and lets measured task accuracy decide. The winner seeds M6's
  ContextCondenser. The 16K-context + aggressive-condense direction (informed by
  NVIDIA "You don't need long context", Belcak et al., arXiv:2611.05306) is a
  hypothesis the bake-off tests, not a settled design. `UniversalFlags.kv_rollback`
  remains the gate for the KV-manipulation path (restricted to full-reset / plain-
  RoPE); the value-managed path works regardless of model class.

### Non-goals (deferred)

- KnowledgeModule and existing-data migration (M6); other domain modules (M7); GUI
  and remote surfaces (M8-M10).
- Draft-model speculative decoding and the full R17 CPU tuning (recorded, not built).
- Replacing the Ollama backend's callers: M5 adds `LlamaCppBackend` as a second
  `IInferenceBackend`; `AgentLoop` (M4) selects a backend. The Ollama backend stays
  for parity cross-checks.

---

## Glossary

- **LlamaCppBackend:** the M5 `IInferenceBackend` linked against the llama.cpp C
  API; owns the model, context, sampler, and the token-level decode loop.
- **KV cache / sequence memory:** llama.cpp's per-sequence key/value store; the
  backend maps `mark_checkpoint`/`rollback_to` onto token positions in it.
- **Prefix pinning:** keeping the KV of the pinned prefix `[0..P]` across a wipe and
  removing only `[P+1..end]` via `llama_memory_seq_rm(mem, seq, P, -1)` (R6).
- **Prefill:** the decode of the prompt tokens before generation begins; its cost is
  what prefix reuse avoids re-paying.
- **GBNF:** llama.cpp's grammar format; a grammar sampler constrains generation so
  only tokens the grammar allows can be emitted.
- **Schema-to-GBNF:** `json_schema_to_grammar(ordered_json)` converting the M2
  action-call JSON schema into a GBNF string.
- **Sampler chain:** the ordered `llama_sampler` pipeline (penalties → top_k → top_p
  → temp → grammar → dist) that turns logits into a token.
- **RAII handle:** a `unique_ptr` with a custom deleter (or a small owning wrapper)
  around a llama.cpp C handle so it frees deterministically (R1).
- **Parity cross-check:** comparing `LlamaCppBackend` output/behavior against the
  M2 `OllamaHttpBackend` on the same model and inputs where meaningful.
- **Vocab-only GGUF:** a tokenizer-only model file (e.g. `ggml-vocab-aquila.gguf`)
  usable for tokenizer/grammar tests without full weights.

---

## Requirements

### Requirement 1: Build and link upstream llama.cpp (pinned)

**User Story:** As the build, I want upstream llama.cpp pinned and fetched like
every other dependency, so the inference backend links against a known-good,
reproducible source (R3, D4).

#### Acceptance Criteria

1. WHEN dependencies are configured THEN upstream `ggml-org/llama.cpp` SHALL be
   declared in the dependency CMake (alongside the other `cmake/Aquila*.cmake`
   modules), pinned by URL + SHA256 (or a pinned tag/commit archive), matching the
   project's existing pinning style.
2. WHEN the GPU-capable lane builds (MSVC) THEN llama.cpp SHALL build with the CUDA
   backend via cl.exe + nvcc (H12), targeting the local sm_89 (RTX 4070).
3. WHEN a sanitizer lane builds (mingw-san / linux-san) THEN the project SHALL still
   configure and build: either llama.cpp builds CPU-only there, or `LlamaCppBackend`
   is compiled out and its tests skipped on that lane, with the choice recorded (see
   Requirement 7). No lane is left broken.
4. WHEN the pinned upstream source is first used THEN M5 SHALL verify whether it
   loads `Qwen3.5-9B-Q4_K_M.gguf` without the fork's local patches, and SHALL record
   the result (loads clean / needs specific patches) as a finding in RECON_MAP; IF
   patches are required THEN the resolution (upstream cherry-pick or documented
   fallback) SHALL be recorded, not silently assumed.

### Requirement 2: Model and context lifecycle with RAII

**User Story:** As a single-user local agent, I want the model and inference
context created and destroyed deterministically with no leaks, so the backend is
safe under the sanitizers and holds VRAM only while in use (R1, R2).

#### Acceptance Criteria

1. WHEN a `LlamaCppBackend` is constructed with a model path and a
   `RuntimeTierConfig`/`ComputeProfile` THEN it SHALL load the GGUF model and create
   a context, offloading `gpu_layers` layers per the tier (0 for CPU tiers, 999 for
   `gpu_high_vram`) (R16).
2. WHEN construction fails (missing file, bad GGUF, out of memory) THEN it SHALL
   report a typed failure (an exception or a documented error state), never a crash
   or a half-initialized object.
3. WHEN a `LlamaCppBackend` is destroyed THEN every llama.cpp handle (model,
   context, sampler, batch, memory) SHALL be freed via RAII, with no raw owning
   pointers and no leaks reported by LSan/CRT (on the lanes that build it).
4. WHEN `num_ctx` is set by the tier or a request THEN the context SHALL be created
   with that size, and a prompt exceeding it SHALL fail with a typed `error_code`
   (e.g. `context_overflow`), not silent truncation.

### Requirement 3: KV-aware context with real checkpoint and rollback

**User Story:** As the ContextCondenser, I want `mark_checkpoint`/`rollback_to` to
manipulate the real KV cache, so a context wipe keeps the pinned prefix's KV and
only re-decodes new tokens (R6, R15).

#### Acceptance Criteria

1. WHEN `append(Message)` is called THEN the backend SHALL tokenize the message
   (with the model's chat template / role formatting) and decode it into the KV
   cache, advancing the sequence position; `supports_kv_reuse()` SHALL return true.
2. WHEN `mark_checkpoint()` is called THEN it SHALL return the current KV sequence
   position (the token count decoded so far), consistent with
   `llama_memory_seq_pos_max`.
3. WHEN `rollback_to(checkpoint)` is called THEN the backend SHALL remove KV entries
   for positions `[checkpoint, end)` via `llama_memory_seq_rm(mem, seq, checkpoint,
   -1)` and reset its logical position to `checkpoint`, so tokens before the
   checkpoint are retained and not re-decoded.
4. WHEN `rollback_to(checkpoint)` is given a checkpoint beyond the current end THEN
   it SHALL throw `std::out_of_range` (the M2 interface contract).
5. WHEN a prefix is decoded, a checkpoint is marked, more tokens are decoded, and
   `rollback_to(checkpoint)` is called on a plain-RoPE model THEN a subsequent
   `generate()` SHALL produce the same result as if the extra tokens had never been
   decoded (rollback is exact). This is proven on a small plain-RoPE CPU model
   (Property 1).
6. WHEN `rollback_to(checkpoint)` targets a mid-sequence position (0 < checkpoint <
   end) on a Qwen 3.5 family model THEN the backend SHALL surface the llama.cpp
   recurrent/M-RoPE inconsistent-position condition as a typed `GenerationResult`
   failure on the next decode, never a crash (M5 FINDING, GPU-proof). Qwen 3.5 is a
   recurrent/hybrid + M-RoPE model and `llama_memory_seq_rm` does NOT rewind
   recurrent/positional state on a partial rollback: a full reset (`rollback_to(0)`)
   is supported, mid-sequence partial rollback is not. The resolution of this
   finding (value-managed context, D14) is decided by the Requirement 9 bake-off and
   consumed by M6.

### Requirement 4: GBNF-constrained structured generation

**User Story:** As the AgentLoop, I want the action-call JSON schema enforced by a
grammar, so the model physically cannot emit malformed JSON and the heal/alias
layer stays unnecessary (R14, R7).

#### Acceptance Criteria

1. WHEN `generate()` is called with `OutputConstraint::json_schema(schema)` THEN the
   backend SHALL convert the schema to GBNF via `json_schema_to_grammar(schema)` and
   add a grammar sampler (`llama_sampler_init_grammar`) to the sampler chain.
2. WHEN `OutputConstraint::json` is used THEN the backend SHALL constrain output to
   generic valid JSON; WHEN `OutputConstraint::none` THEN no grammar sampler is added.
3. IF `json_schema_to_grammar` or `llama_sampler_init_grammar` fails (NULL grammar)
   THEN `generate()` SHALL return `GenerationResult{ok=false,
   error_code="invalid_request"}` with the detail, not crash.
4. WHEN the action-call schema `{thought, module, action, args}` is enforced over N
   >= 50 generations with varied prompts THEN every output SHALL parse as a valid
   `ActionCall` via the M1 `parse<ActionCall>` (invalid JSON impossible), which is
   the M5 proof-of-done "invalid JSON impossible in N trials".
5. WHEN the sampler chain is built THEN it SHALL honor `GenerationParams`
   (temperature, top_k/top_p if set, repeat_penalty/repeat_last_n, seed) in the
   conventional llama.cpp order, with a fixed seed yielding deterministic output.


### Requirement 5: Prefix reuse measurably cheaper than a full resend

**User Story:** As a user on a serial GPU, I want a context wipe to re-decode only
the new tokens, so the agent does not re-pay the whole prefill after every
condense (R6, the "Hidden Hardware Win").

> **Scope (M5 FINDING).** Prefix reuse via mid-sequence KV retention is demonstrated
> on a plain-RoPE model (Property 8, CPU). On Qwen 3.5 (recurrent/M-RoPE) the
> mid-sequence wipe is unsupported (Requirement 3.6); the savings this requirement
> claims are therefore realized on Qwen 3.5 only via a full-reset + value-managed
> re-decode, whose strategy is chosen by the Requirement 9 bake-off. The GPU live
> test records this honestly rather than asserting an unsupported partial rollback.

#### Acceptance Criteria

1. WHEN a prefix is pinned, generation proceeds, and a wipe rolls back to the prefix
   checkpoint THEN resuming generation SHALL decode only the post-checkpoint tokens,
   NOT re-decode the pinned prefix.
2. WHEN the post-wipe prefill is measured (tokens decoded, or a prefill token/time
   counter) THEN it SHALL be strictly less than decoding the full prompt from token
   0, which is the M5 proof-of-done "post-wipe prefill token count measured < full
   prompt".
3. WHEN the same logical conversation is run with prefix reuse vs. a full resend
   THEN the generated continuation SHALL be equivalent (reuse is a performance
   optimization, not a behavior change) within the model's determinism for a fixed
   seed.

### Requirement 6: Streaming, cancellation, timeout, and typed errors

**User Story:** As a caller, I want the same streaming and typed-outcome contract
the M2 backend provides, so the AgentLoop and future GUI work against one interface
regardless of backend (R15, M2 parity).

#### Acceptance Criteria

1. WHEN `generate()` is called with a non-empty `TokenCallback` THEN the backend
   SHALL invoke it per decoded token (content, and thinking if the model emits a
   think channel), and WHEN the callback returns false THEN generation SHALL stop
   and return `GenerationResult{ok=false, error_code="cancelled"}`.
2. WHEN generation reaches the model's EOS or `max_tokens` THEN it SHALL stop with
   `ok=true` and a `done_reason` ("stop" / "length").
3. WHEN no token is produced within `timeout_s` THEN it SHALL return
   `error_code="stream_stalled"` (matching the M2 error vocabulary where it applies).
4. WHEN `generate()` returns THEN the backend's KV state SHALL be unchanged from
   before the call (the reply is not appended; the caller appends it to keep it),
   matching the M2 contract, and `prompt_tokens`/`completion_tokens` SHALL be
   populated.
5. WHEN the backend reports its `ComputeProfile` THEN `active_profile()` SHALL
   reflect the tier it was created for, and a `LlamaCppBackend` SHALL report
   `supports_kv_reuse() == true`.

### Requirement 7: Cross-lane build strategy and sanitizer safety

**User Story:** As the CI/build owner, I want M5 to keep all five lanes and the
three CI jobs green, so adding a heavyweight native dependency does not break the
sanitizer or cross-compiler guarantees established in M0-M4 (R4).

#### Acceptance Criteria

1. WHEN M5 lands THEN the five lanes (`msvc-release`, `msvc-asan`,
   `msvc-release-cuda`, `mingw-san`, `linux-san`) and the three CI jobs SHALL all
   configure, build, and pass on a fresh clone.
2. WHEN the backend cannot be built on a lane (e.g. CUDA under clang) THEN the lane
   SHALL build `LlamaCppBackend` CPU-only or compile it out behind a documented
   build option, and the tests that need it SHALL skip cleanly on that lane (as the
   live tests already skip in CI), never fail to compile.
3. WHEN `LlamaCppBackend` is exercised under a sanitizer lane that builds it
   (CPU-only) THEN ASan/UBSan/LSan SHALL report nothing on real code, using a small
   model (a vocab-only or tiny GGUF) so the sanitizer run stays fast.
4. WHEN the GPU path and the full-model live behavior are verified THEN those tests
   SHALL be opt-in (like the M2 live tests, `-DAQUILA_LIVE_TESTS=ON`) and excluded
   from CI; CI verifies only what is portable and fast.

### Requirement 8: Verification, parity, and R20 accounting

**User Story:** As a reviewer who never accepts "done" without proof, I want each
M5 claim backed by a repeatable check, so correctness is demonstrated across lanes.

#### Acceptance Criteria

1. WHEN M5 is verified THEN tests SHALL cover: RAII lifecycle / no leaks (Req 2),
   checkpoint/rollback exactness including the out-of-range throw (Req 3), GBNF
   validity over N >= 50 generations (Req 4), the post-wipe-prefill-< -full-prompt
   measurement (Req 5), and streaming/cancel/timeout/typed-error outcomes (Req 6).
2. WHEN grammar and tokenizer behavior is tested on a sanitizer lane THEN it SHALL
   use a small/vocab-only GGUF so the test is CI-fast and deterministic; the
   full-weight `Qwen3.5-9B-Q4_K_M.gguf` is reserved for the opt-in GPU/live tests.
3. WHEN the GBNF "invalid JSON impossible" and the prefix-reuse savings are proven
   THEN they SHALL run as opt-in live/GPU tests against the real model, and the
   measured numbers (N trials with 0 invalid; post-wipe vs full prefill token
   counts) SHALL be recorded.
4. WHEN M5 can cross-check against Ollama THEN a parity test SHALL compare
   `LlamaCppBackend` and `OllamaHttpBackend` behavior on the same model/prompt where
   meaningful (e.g. both honor the action-call schema; both are deterministic at a
   fixed seed), and any divergence SHALL be recorded as an explained finding (R19).
5. WHEN M5 completes THEN RECON_MAP SHALL gain a section (8.5) of per-feature
   verdicts against Python's `OllamaClient` and the design's R15 interface, record
   `UniversalFlags.kv_rollback`/`gbnf` flipped to true for this backend, note the
   R17 CPU-engine items deferred, record the upstream-vs-fork Qwen 3.5 finding, and
   state the R20 line count (C++ added vs the Python it replaces — the remainder of
   `OllamaClient` plus the parser/heal paths a grammar makes unnecessary).
6. WHEN the S7 KV API note in RECON_MAP section 2.2 is revisited THEN it SHALL be
   confirmed against the upstream header actually built (not only the local fork),
   closing the "verify again against upstream at M5" action.

### Requirement 9: Context-strategy bake-off (decides D14)

**User Story:** As a reviewer who never accepts "done" without proof, I want the
context-management strategy chosen by measured task accuracy on the real Qwen 3.5
family, so the M6 ContextCondenser is built on evidence rather than on the
assumption that broke when Qwen 3.5's M-RoPE cache could not do mid-sequence
rollback (Requirement 3.6, D14).

#### Acceptance Criteria

1. WHEN the bake-off is set up THEN three strategies SHALL be implemented behind a
   single kept `ContextStrategy` interface (not throwaway harness code), so the
   winner becomes M6's starting point:
   a. **KV-rollback** (the original R6 design, control): `mark_checkpoint` +
      mid-sequence `rollback_to`. Expected to be disqualified on Qwen 3.5 by the
      M-RoPE finding; retained as the baseline and as the plain-RoPE reference.
   b. **EoCC** (End-of-Context Compaction): let context grow to a threshold
      (default 16K), then condense the message list and rebuild, relying on
      llama.cpp automatic prefix caching; no mid-sequence KV surgery.
   c. **SAC** (Single-Action-per-Context): a fresh context per action, fed an
      aggressively summarized state each turn; dissolves the M-RoPE constraint by
      construction.
2. WHEN the bake-off runs THEN it SHALL score each strategy on a shared task suite
   of 5-10 multi-turn tool-use tasks designed to force long context (information
   established in early turns must be recalled after many intervening tool calls),
   so compaction fidelity is actually stressed (the behavior the NVIDIA paper
   measured, not a shallow smoke test).
3. WHEN each run is measured THEN the harness SHALL record, per strategy per model:
   task-completion rate, tokens decoded per task, wall-clock latency per task,
   crash/typed-failure rate, and a summarization-fidelity check (did condensing
   drop information the agent later needed), all written to a recorded results
   artifact.
4. WHEN the models are selected THEN the bake-off SHALL decide on **Qwen 3.5 4B
   Q4_K_M (CPU)** — the CPU-first default and the deciding lane — and SHALL record
   **Qwen 3.5 9B Q4_K_M (GPU)** as a confirmation lane that is non-gating (M5 may
   close on the 4B decision; the 9B run is recorded whenever the GPU is free). The
   4B GGUF SHALL be pinned by URL + SHA256 like the 9B and the tiny test model.
5. WHEN the winner is chosen THEN the decision SHALL follow a pre-committed rule,
   applied to the 4B CPU results: **accuracy first** (highest task-completion rate
   wins); **cost as tiebreaker** (fewest tokens decoded, then lower latency, breaks
   an accuracy tie); **any crash disqualifies** (a strategy that crashes — as
   opposed to a typed failure — on any task is removed from contention). The rule
   is fixed before results are read, so the outcome is not rationalized after the
   fact.
6. WHEN the bake-off completes THEN its result SHALL be recorded in RECON_MAP as the
   resolution of the Qwen 3.5 M-RoPE finding and of D14: the winning strategy, the
   measured numbers behind the decision, the disqualified/rejected strategies with
   why, and the explicit hand-off to M6 (the winning `ContextStrategy` is M6's
   ContextCondenser starting point).
7. WHEN the bake-off touches generation THEN it SHALL reuse the M5 `LlamaCppBackend`
   (GBNF action calls, full-reset rollback, the `prefill_tokens` counter) unchanged
   — the bake-off compares context-management strategies layered on the backend, it
   does not fork the backend.

---

## Traceability

| Requirement | Governing | Source / oracle |
|---|---|---|
| 1 Build upstream llama.cpp | R3, D4, H12 | `cmake/Aquila*.cmake`; upstream `ggml-org/llama.cpp` |
| 2 Model/context RAII | R1, R2, R16 | `llama.h` model/context/`llama_batch` |
| 3 KV checkpoint/rollback | R6, R15 | `llama_memory_seq_rm`/`_pos_max`; M2 `IInferenceBackend` |
| 4 GBNF structured output | R7, R14 | `json_schema_to_grammar`, `llama_sampler_init_grammar`; M1 `ActionCall` |
| 5 Prefix reuse savings | R6 | design "Hidden Hardware Win" (D:L; KV-cache prefix pinning) |
| 6 Streaming/errors | R15 | M2 `GenerationParams`/`GenerationResult` contract |
| 7 Cross-lane build | R4, H12 | M0 lane table (RECON_MAP section 1) |
| 8 Proof & R20 | R19, R20, S7 | fixture/live method (sections 8.2-8.4); `OllamaClient` |
| 9 Context-strategy bake-off | D14, R6, R7, R18 | GPU M-RoPE finding; NVIDIA arXiv:2611.05306; M6 ContextCondenser |
