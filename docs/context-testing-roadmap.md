# Model / context testing roadmap (user plan)

Ordered evaluation ladder for Aquila tier and summarization design:

1. **32k non-TQ** — primary test bed until satisfied with behavior, speed, and long-horizon via summary/scratchpad.
2. **16k non-TQ** — next step down; validate framework at standard compact context.
3. **16k TQ** — stress test; very small window; use results to shape tiers and framework strategy around real limits.

Implications for framework work:

- Tune `ContextProfile` / `in_step_token_cap` / workspace summary / proactive compress for **16k+** horizons, not only `max` (96k).
- Expect faster, more coherent turns at 32k/16k non-TQ vs TQ-96k.
- Control issues (e.g. `mark_objective_complete` not in `tools[]`, episode stall) are orthogonal to context size.

Suggested env while testing:

- `OLLAMA_MODEL` = non-TQ aquila (or project default) with `OLLAMA_NUM_CTX` matching target (32768, then 16384).
- Optional: `AQUILA_CONTEXT_TIER=standard` or `extended` to align with 32k; revisit after 16k runs.
