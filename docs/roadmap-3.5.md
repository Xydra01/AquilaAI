# Aquila OS 3.5 — Roadmap

## Prerequisite

3.4 workspace QA complete, including Character AI ([workspace-qa-cai.md](workspace-qa-cai.md)) and core workspaces ([workspace-qa-3.4.md](workspace-qa-3.4.md)).

## Primary goal: Learn mode

Replace the Learn stub ([`agent/gui_pages/stub_page.py`](../agent/gui_pages/stub_page.py)) with a classroom-style workspace:

- Course list / enrollment home
- Assignments and due dates
- Progress tracking per learner
- Integration with Aquila instances (each class may map to an instance or profile)

### Suggested milestones

1. **M1 — Learn shell** — `LearnPage` with home layout (courses grid, placeholder data), wire `gui.py` stack (no agent tasks yet).
2. **M2 — Course model** — filesystem or JSON under `Agent-Instances/{id}/learn/` (courses, modules, assignments).
3. **M3 — Agent hooks** — optional tutor task mode (read-only recon + explain, no destructive tools).

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
