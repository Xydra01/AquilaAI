# Aquila OS 3.5 — Roadmap

## Prerequisite

3.4 workspace QA complete, including Character AI ([workspace-qa-cai.md](workspace-qa-cai.md)) and core workspaces ([workspace-qa-3.4.md](workspace-qa-3.4.md)).

## Primary goal: Learn mode (dual MVP — shipped in 3.5 alpha)

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

## Out of scope for 3.5

| Item | Target |
|------|--------|
| MCP bridge | 4.0 ([`agent/mcp_bridge.py`](../agent/mcp_bridge.py) stub) |
| Inter-modal orchestration | Future (Task mode placeholder stack today) |
| Embedded browser in Research | Deferred (SearXNG panel remains) |

## Branch / release

- Development branch: `Aquila-3.5`
- QA checklist: [workspace-qa-3.5.md](workspace-qa-3.5.md)

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) §18 — mode workspaces
- [README.md](../README.md) § Known limitations and 3.5 direction
