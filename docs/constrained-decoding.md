# Constrained decoding (Track A)

Aquila pushes loop policy into **JSON Schemas** sent to Ollama as the top-level `format` field. Ollama compiles schemas to **GBNF** and masks invalid tokens during sampling — native constrained decoding without Guidance.

## Components

| Module | Role |
|--------|------|
| [`agent/policies/schema_policy.py`](../agent/policies/schema_policy.py) | `TurnSchemaSpec` — per-turn allowlists, `maxItems`, `finish_task` omission |
| [`agent/parser/structured_schema.py`](../agent/parser/structured_schema.py) | `build_agent_action_json_schema`, optional `build_turn_type_schemas` (oneOf-style branches) |
| [`agent/core/loop_engine.py`](../agent/core/loop_engine.py) | `_schema_for_step` → SchemaPolicy → Ollama |
| [`docs/thinking.md`](thinking.md) | Two-phase act loop (think pass + JSON act pass) |

## Environment

| Variable | Default | Role |
|----------|---------|------|
| `AQUILA_ACT_TWO_PHASE` | `1` | Think pass then structured act per loop tick |
| `AQUILA_ACT_STRUCTURED_NO_PLAIN` | `1` | Act turns: no plain-text structured fallback |
| `AQUILA_DYNAMIC_LOOP` | `0` | Milestone-driven work palette (see [loop-dynamic.md](loop-dynamic.md)) |

## Decode-time rules (examples)

- **Not final step:** `finish_task` omitted from schema
- **Research search step (legacy loop):** `tools.maxItems: 1`
- **Final step + dynamic milestones incomplete:** `finish_task` omitted until tracker allows

Residual **OS BLOCK** messages remain for runtime caps, path registry, and duplicate detection.

## Tests

```bash
cd agent && python -m pytest tests/test_schema_policy.py tests/test_loop_settings.py -q
```

See also [structured-output.md](structured-output.md) and [planning-and-artifacts.md](planning-and-artifacts.md).
