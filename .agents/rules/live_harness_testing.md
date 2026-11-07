# Mandatory Live Evaluation & Hardening Rule
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
