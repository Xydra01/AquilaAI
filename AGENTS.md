# Aquila AI Framework Development Rules

## Mandatory Live Evaluation & Hardening Rule
All new features, capabilities, recipes, module actions, prompt templates, and bug fixes MUST be empirically verified and hardened using the recursive live evaluation harness (`scripts/live_eval_harness.py` / `aquila eval --live`) on real hardware before being considered done:

1. **Reality Over Theoretical Implementation:**
   - Theoretical correctness, compilation success, and mock tests are necessary but insufficient on their own.
   - Every feature must be validated against real in-process model execution (e.g., `llama.cpp` CUDA backend with target model weights on GPU).
   - Scrutinize the agent's actual multi-turn thought trajectory, action parameters, module resolution, and tool outputs. Ensure reality matches expectations:
     - No action repetitions or multi-turn oscillation.
     - No hallucinated modules or unexposed action calls.
     - No token framing defects (e.g., redundant BOS tokens, role inversions, or premature truncation).
     - Deterministic exit gates must pass with validated ground-truth artifacts.

2. **Recursive Test-Diagnose-Adjust-Repeat Protocol:**
   - **Step 1: Test** — Run live evaluation with `python scripts/live_eval_harness.py --recipe <recipe> --backend llama --model <model_path> --tier gpu`.
   - **Step 2: Autopsy** — Inspect the autopsy report (`eval_report.json`), flags, and thought traces.
   - **Step 3: Adjust** — Address root causes directly in the C++ core engine, schema constraints, or prompt framing.
   - **Step 4: Re-verify** — Rebuild and repeat the harness run until 100% pass rate is achieved.

3. **Regression Testing & Quality Gates:**
   - Ensure all Catch2 and RapidCheck property test cases pass (`tests/unit/aquila_unit_tests.exe`).
   - Verify that all affected multi-domain recipes pass without regressions across domains (`dev`, `research`, `writing`, `persona`, `learn`).

4. **Mandatory Live Output Utility & Substance Assessment:**
   - In addition to zero structural errors (repeats, hallucinations, syntax), you MUST inspect and assess the actual substance, execution, and utility of generated deliverables during every live evaluation or debug run:
     - **Dev**: Generated scripts must execute cleanly in the workspace virtual environment with exit code 0, have valid ASTs without stub bodies (`pass`, `# TODO`, `raise NotImplementedError`), and fulfill functional requirements.
     - **Research**: Reports must contain structured sections (Summary, Findings, Citations), substantive length (> 350 chars), and verifiable citations, backed by recorded facts in SQLite `FactStore`.
     - **Writing**: Manuscripts must meet depth thresholds (> 500 chars/section) with zero unexpanded placeholder tokens (`TODO`, `Lorem ipsum`, `[TBD]`).
     - **Learn**: Syllabi must have hierarchical depth (>= 8 units, >= 5 sub-units) with unique pedagogical titles; archive Q&A answers must ground claims in cited passages.
     - **Persona**: Profiles must satisfy the 800+ character depth gate, establish complete voice/lore bibles, and pass anti-assistant leakage screening.
   - Never accept a run as passed if what the agent created is unusable, superficial, or fails functional execution.
