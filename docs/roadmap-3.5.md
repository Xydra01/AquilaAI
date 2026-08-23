# Aquila OS 3.5 — Roadmap

## Prerequisite

3.4 workspace QA complete, including Character AI ([workspace-qa-cai.md](workspace-qa-cai.md)) and core workspaces ([workspace-qa-3.4.md](workspace-qa-3.4.md)).

## Primary goal: Learn mode (dual MVP — shipped in 3.5)

Replace the Learn stub with **Classroom + Archives** ([`docs/learn-mode.md`](learn-mode.md)):

- **Classroom:** courses, `syllabus.json` ledger, mastery tiers 0–5, Socratic tutor, assessments
- **Archives:** source upload, Chroma index, grounded chat, quiz/study markdown export

### Delivered

1. `LearnPage` — home, course create (3 intakes), classroom tree + tutor + assessment, archive workspace
2. `learn_registry.py` / `learn_index.py` / `learn_tools.py` — instance-scoped storage and indexing
3. Agent modes: `learn_syllabus_build`, `learn_tutor`, `learn_archive_chat`

### Post-MVP (3.5b / 3.6)

- Assignment calendar / due dates
- Rich placement diagnostic
- Writing Mode subcall for polished exports
- Slides / images

## Also shipped in 3.5

| Item | Location |
|------|----------|
| MCP client bridge | [`agent/core/mcp_bridge.py`](../agent/core/mcp_bridge.py) — [mcp-integration.md](mcp-integration.md) |
| MCP host (Cursor) | [`agent/core/mcp_host.py`](../agent/core/mcp_host.py) — [aquila-mcp-host.md](aquila-mcp-host.md) |
| Remote Companion | [`agent/remote/`](../agent/remote/) — [remote-companion.md](remote-companion.md) |
| Runtime Settings GUI | [`agent/gui/gui_pages/settings_page.py`](../agent/gui/gui_pages/settings_page.py) |
| Dynamic loop + harness | [loop-dynamic.md](loop-dynamic.md), [aquila-recursive-harness.md](aquila-recursive-harness.md) |
| Codebase refactor | Subpackages under `agent/core/`, `storage/`, `parser/`, `policies/`, `research/`, `coding/`, `gui/` |

## Experimental / disabled by default

| Item | Notes |
|------|-------|
| Data Processing mode | `AQUILA_ENABLE_DATA_PROCESSING=0` — [data-processing-mode.md](data-processing-mode.md) |
| CNN training toolkit | Local only — [vision-and-cnn.md](vision-and-cnn.md) |

## Out of scope for 3.5 (deferred to 4.0+)

| Item | Target |
|------|--------|
| Inter-modal orchestration UI | 4.0 — [roadmap-4.0.md](roadmap-4.0.md) Pillar D |
| Voice-first operation | 4.0 — [voice-interface-vision.md](voice-interface-vision.md) |
| ML Lab (Data Processing evolution) | 4.0 — [ml-lab-vision.md](ml-lab-vision.md), `aquila[ml]` extra |
| Voice (wake + toggle) | 4.0 — [voice-interface-vision.md](voice-interface-vision.md), `aquila[voice]` extra |
| Smart home integration | Vision only — [smart-home-vision.md](smart-home-vision.md); no 4.0 code |
| Lifestyle / Communication / Workflow editor | 4.0 — [roadmap-4.0.md](roadmap-4.0.md) Pillars F, G, D |
| Prompt suggestion (all typing surfaces) | 4.0-cross — [prompt-suggestion-vision.md](prompt-suggestion-vision.md) |
| Embedded browser in Research | Deferred (SearXNG panel remains) |
| Multi-GPU worker scheduler | 5.0 — [loop-rework-and-parallelism.md](loop-rework-and-parallelism.md) |

## Branch / release

- Development branch: `Aquila-3.5`
- QA checklist: [workspace-qa-3.5.md](workspace-qa-3.5.md)

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — mode workspaces
- [README.md](../README.md) — operational modes
