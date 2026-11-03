# Structured output (Pydantic + Ollama)

Aquila generates **strict JSON Schema** from tool signatures via Pydantic and sends it to Ollama native `/api/chat` as the top-level `format` field (same schema body). Parsed responses are validated with the same models before tools run. See also [thinking.md](thinking.md) for `message.thinking` vs JSON `reasoning`, and [constrained-decoding.md](constrained-decoding.md) for SchemaPolicy / decode-time rules.

## Surfaces

| Surface | Schema | Parser |
|---------|--------|--------|
| Act loop | Routed per-step tool subset | `parse_agent_response` + Pydantic |
| Plan | `TaskPlanModel` | `parse_agent_response(schema_kind=task_plan)` |
| Explore brief | Same as act (explore tools only) | Same |
| Reflect (legacy act) | `ReflectTurnModel` | `parse_agent_response(schema_kind=reflect)` |

## Model profiles

`OLLAMA_MODEL` selects a capability profile (`aquila`, `qwopus`, `heretic`, `turboquant`):

| Profile | Notes |
|---------|--------|
| `aquila` | Full strict → shrink → `json_object` → plain |
| `qwopus` | Same as `aquila` (Qwopus Coder tag `aquila_qwopus`) |
| `heretic` | Same; smaller default routed schema cap |
| `turboquant` | Stricter plain fallback via `AQUILA_STRUCTURED_NO_PLAIN=1` |

## Environment

| Variable | Default | Role |
|----------|---------|------|
| `AQUILA_STRUCTURED_STRICT` | `1` | Use strict schema dict as first `format` attempt |
| `AQUILA_STRUCTURED_NO_PLAIN` | `0` | If `1`, skip plain-text fallback after schema/json_object failures |
| `AQUILA_SCHEMA_MAX_TOOLS` | profile default | Max tools in one routed schema `anyOf` |
| `AQUILA_CAPABILITY_SCHEMA_ENRICH` | `1` | Tier A: embed per-cap Pydantic argument schemas when the step has ≤ `AQUILA_CAPABILITY_SCHEMA_ENRICH_MAX` action caps (plan checklist caps excluded from the count) |
| `AQUILA_CAPABILITY_SCHEMA_ENRICH_MAX` | `5` | Max action capabilities for Tier A enriched schema |

## Capability act turns

Capability modes (code, research, writing, learn, persona) use `build_capability_action_json_schema()` instead of the legacy tool-path schema.

| Tier | When | Schema shape |
|------|------|--------------|
| **A** | ≤ `AQUILA_CAPABILITY_SCHEMA_ENRICH_MAX` action caps (default 5); `cap.plan.*` checklist caps excluded from the count but included in branches | `capabilities[].items` uses `anyOf` with `{ id: const, arguments: <Pydantic schema> }` per allowed cap |
| **B** | Larger allowlists (e.g. code `work` ~10 caps) | Flat `id` enum + freeform `arguments`; **Capability argument shapes** hints in step entry and think anchor on `invalid_input` / OS block |

Set `AQUILA_CAPABILITY_SCHEMA_ENRICH=0` to force flat schemas everywhere. On HTTP 400 from an enriched branch, add the cap id to `AQUILA_CAPABILITY_SCHEMA_ENRICH_BLOCKLIST` (comma-separated).

Argument validation always runs in `run_capability()` regardless of tier.

## JSON healing

The stack-based JSON healer in `parse_agent_response` runs **only** when the request used `json_object` or plain mode—not after a successful strict-schema response.

## Assistant prefill (important)

Do **not** send an assistant message that starts `{"reasoning": "` when using strict `json_schema`. Ollama returns a complete JSON object; prefill makes some models (including TurboQuant builds) continue with plain prose instead of JSON. The act loop and explore brief omit prefill when `format` is a schema dict.

## Live tests

```bash
cd agent && python -m pytest tests/test_structured_output_metrics.py -m live -q
```

Requires Ollama up and `OLLAMA_MODEL` present. Uses `AQUILA_LIVE_STRUCTURED_TRIALS` (default 20). Fails fast with a clear message if the server is down.

## Metrics

JSONL events (when `AQUILA_LOG_JSON=1`):

- `structured_schema_request` — tool count, schema size, profile
- `structured_parse` — `ok`, `healed`, `format_mode`, `error_kind`

## Troubleshooting

| Symptom | Action |
|---------|--------|
| HTTP 400 on chat | Schema too large—reduce routed tools or set `AQUILA_SCHEMA_MAX_TOOLS=10` |
| Valid JSON but schema violation | Check tool `name` matches routed set; use OS task name for scratchpad tools |
| Heretic returns strings for ints | Pydantic coerces at execution; add `int` annotations on new tools |
| TQ drops strict often | Run TurboQuant server from PR build; try `AQUILA_STRUCTURED_NO_PLAIN=1` |

## Tests

```bash
cd agent && python -m pytest tests/test_structured_output.py tests/test_ollama_client.py -q
# Live matrix (optional):
python -m pytest tests/test_structured_output_metrics.py -m live -q
```
