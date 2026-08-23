# Workflow editor vision (Aquila 4.0)

**Status:** Draft — planning document only.

**Relationship:** User-facing layer on **[Pillar D — Orchestration](roadmap-4.0.md)**. The engine (delegation, artifact handoff, `ModeRunner`) ships in **4.0a**; the workflow editor is the visual builder that makes it reusable without re-prompting every time.

## Goal

An **advanced, block-style editor** where users compose, save, and rerun multi-step Aquila workflows:

- Pick **modes** (Chat, Research, Code, Writing, ML Lab, …) as nodes
- Attach **per-node prompts** or parameter templates
- Configure **handoffs** — which artifacts, summaries, or files pass to the next node
- **Save / duplicate / export** workflows for one-click reuse (Autonomous Task, voice, or Remote Companion later)

## Principles

1. **Same runtime as Task mode** — saved workflows compile to the existing delegation + ledger model; no second execution engine.
2. **Serial by default** — matches 4.0 generation lock (one GPU job at a time). Parallel branches are a **5.0** concern.
3. **Explicit data contracts** — each edge declares what crosses (scratchpad export, deliverable path, user attachment, none).
4. **Versioned saves** — workflows live under `Agent-Instances/{id}/workflows/` as JSON; GUI edits never mutate running ledgers in place.

## MVP checklist (4.0a — with orchestration stack)

- [ ] Workflow JSON schema (nodes, edges, mode, prompt template, handoff spec)
- [ ] List / open / save / duplicate in GUI
- [ ] Run workflow from editor → Autonomous Task with pre-filled delegation plan
- [ ] Handoff presets: `deliverable_only`, `scratchpad_export`, `full_summary`, `none`
- [ ] One bundled example workflow (e.g. Research → Writing)

## Stretch (4.x)

- [ ] Sub-workflows / nested graphs
- [ ] Conditional edges (“if research found N sources → …”)
- [ ] Schedule trigger from **Lifestyle** calendar ([lifestyle-vision.md](lifestyle-vision.md))
- [ ] Voice: “Run my weekly research workflow”
- [ ] Remote Companion: run saved workflow from PWA

## Non-goals (4.0)

- Visual programming of arbitrary Python
- Parallel node execution on one GPU
- Zapier-style cloud integrations (see [communication-vision.md](communication-vision.md) for comms-specific scope)

## See also

- [roadmap-4.0.md](roadmap-4.0.md) — Pillar D
- [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md) — artifact bus, scratchpad handoff
