# Capability Modules Vision

Aquila is moving from **LLM-orchestrated raw tools** to **code-orchestrated capabilities** for high-friction modes. **Research is the reference implementation** — capability-only, no legacy tool act path. **Character build and Learn syllabus build** are also on the capability act path via `LoopEngine.CAPABILITY_ACT_MODES`.

## Layer model

```
Tools (web_search, save_research_note, …)
  → Tool modules (web_tools, agent_tools, persona_tools, learn_tools)
    → Capabilities (batched Python orchestration, one LLM call per turn)
      → Function modules / recipes (fn.research.*, fn.persona.*, fn.learn.*)
        → Modes (Research / Character / Learn pages, MCP, chat add-ons)
```

## Design rules

1. **Code orchestrates** — recipes and capabilities run many tool calls inside Python; the LLM picks among ~5–7 capabilities per turn, not ~14 tools.
2. **Batch inside capabilities** — e.g. `cap.research.gather_web_sources@v1` runs search, auto-scrape, read, register sources, and append notes in one act turn.
3. **Composer / recipes** — `agent/functions/recipes.py` maps intent to capability sequences (`full_pipeline`, persona/learn recipes, etc.).
4. **Capability-only act modes** — Research, `character_build`, and `learn_syllabus_build` emit `capabilities[]`; raw tools stay inside handlers.
5. **Versioned IDs** — capabilities use stable IDs like `cap.research.gather_web_sources@v1`.

## Why capabilities replace tools in the act loop (ADR)

| Problem with raw tools | Capability approach |
|------------------------|---------------------|
| Large JSON schemas (14+ tools per turn) | ~5–7 capability IDs per step |
| LLM must orchestrate multi-step web flows | Python batches search → read → note in one turn |
| Hard to test policy offline / milestone gates | Policy validates capability IDs; milestones map from cap runs |
| Duplicate logic in prompt + loop + tools | Single handler + recipe defaults |

## Research capability catalog (v1)

| Tier | ID | Role |
|------|-----|------|
| A | `cap.web.search@v1` | SearXNG search |
| A | `cap.web.read_pages@v1` | Fetch URLs |
| A | `cap.research.append_note@v1` | Scratchpad notes |
| A | `cap.research.read_notes@v1` | Read notes |
| A | `cap.research.register_sources@v1` | Bibliography registry |
| B | `cap.research.ingest_offline@v1` | Journal + attachments |
| B | `cap.research.gather_web_sources@v1` | Core online research step |
| B | `cap.research.synthesize_notes@v1` | Notes → synthesis |
| B | `cap.research.compile_report@v1` | Notes → markdown body |
| B | `cap.research.finalize_deliverable@v1` | Write `Agent-Research/*.md` |
| B | `cap.research.light_web_context@v1` | Chat-mode light web context |
| C | `cap.plan.generate_research@v1` | Template plan with capability steps |
| D | `cap.research.explore_brief@v1` | Pre-plan brief |
| D | `cap.dev.raw_tool@v1` | Debug escape hatch |

## Act-turn JSON (research / 3.5 capability contract)

```json
{
  "reasoning": "string",
  "capabilities": [
    {"id": "cap.research.gather_web_sources@v1", "arguments": {"topic": "…"}}
  ],
  "final_report": "optional on finalize step"
}
```

**3.5 act contract** (shared by Research now; later modes reuse the same builder):

1. Ollama `format` schema is **flat**: `capabilities[].id` is an `enum` of allowed IDs; `arguments` is a freeform object. Per-capability Pydantic models validate args inside `run_capability` — do not embed per-cap input trees (`anyOf` / `const`) in the Ollama schema.
2. **Never** pair an assistant JSON prefill with a JSON Schema `format` dict (stock Ollama → HTTP 400 `Failed to initialize samplers`). Prefill is only for non-schema formats (`json_object` / plain).
3. Builder: `build_capability_action_json_schema` + parse `schema_kind="capability_action"`.

## Plan steps

Template and fallback plans include `capability_id`, optional `params`, and `capability_recipe`:

```json
{
  "step_kind": "search",
  "capability_id": "cap.research.gather_web_sources@v1",
  "params": {"topic": "…"},
  "capability_recipe": "fn.research.full_pipeline",
  "max_iterations": 4
}
```

Legacy `step_kind` values map to default capabilities via `agent/capabilities/adapters.py`.

## Reference implementation checklist (Research)

Use this when migrating another mode:

| Layer | Research artifact |
|-------|-------------------|
| Registry | `agent/capabilities/research/*`, `agent/capabilities/registry.py` |
| Mode adapter | `agent/capabilities/adapters.py` — `default_capability_for_step`, `allowed_capabilities_for_step` |
| Act schema | `build_capability_action_json_schema` + `schema_kind="capability_action"` |
| Step policy | `CapabilityResearchPolicy` in `agent/policies/step_policies.py` |
| Milestones | `MilestoneTracker.record_capability()` in `agent/core/loop_objectives.py` |
| Recipes | `agent/functions/recipes.py` + `agent/functions/research.py` |
| Plan layer | `plan_validator.py` expanders attach `capability_id`; recipe-first fallback |
| Surfaces | Explore brief + chat light web via caps; MCP `aquila_run_research_capability` |
| Tests | `test_research_capability_parity.py` go/no-go suite |

Optional QA: `AQUILA_RESEARCH_RECIPE_STRICT=1` auto-runs step `capability_id` on first act turn.

## Migration playbook (next modes)

| Order | Mode | Capability domain | Status |
|-------|------|-------------------|--------|
| 1 | Research | `cap.research.*`, `cap.web.*` | Done (reference) |
| 2 | character_build / learn_syllabus | `cap.persona.*`, `cap.learn.*` | Done — `CAPABILITY_ACT_MODES`; plan, act-hint, and fallback layers are capability-first (same contract as research) |
| 3 | writing | `cap.writing.*` | Next |
| 4 | code | `cap.dev.*` composites | Pending |
| 5 | task/autonomous | `cap.delegate.*` recipes | Pending |

Shared gate: `LoopEngine.CAPABILITY_ACT_MODES` / `_uses_capability_act()` — add a mode string when migrating.

Steps for each mode:

1. Register capabilities with Pydantic inputs and handlers.
2. Add adapter table entries (default + allowed caps per step_kind).
3. Switch act schema to `capability_action` for that mode only.
4. Implement `Capability*Policy` with forbidden caps + validate + auto-advance.
5. Wire `record_capability()` milestone mapping.
6. Attach `capability_id` in plan expanders; add recipe fallback.
7. Expand parity tests before deleting tool act path.

## MCP export

When using the Aquila MCP host:

- `aquila_list_research_capabilities` — list registered caps
- `aquila_run_research_capability` — run one cap with JSON arguments

## Testing

Go/no-go suite:

```bash
python -m pytest agent/tests/test_research_capability_parity.py agent/tests/test_character_capability_parity.py agent/tests/test_learn_capability_parity.py agent/tests/test_capabilities_*.py agent/tests/test_research_capability_loop.py -q -m "not live"
```

- Unit: `test_capabilities_primitives.py`, `test_capabilities_composites.py`
- Foundation: `test_capabilities_foundation.py`
- Loop/schema: `test_research_capability_loop.py`
- Character/Learn: `test_character_capability_parity.py`, `test_learn_capability_parity.py`
- Policy/offline: `test_offline_research.py`

## Out of scope (follow-on)

- Writing / code / task capability migration (items 3–5)
- Global removal of raw tool act loop in non-capability modes
- Workflow editor UI (4.0) — capability IDs become block types there
- Tutor-time learn tools (mastery / archive) as capabilities
