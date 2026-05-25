# Workspace QA — Aquila 3.5 (Learn mode)

Run when Learn workspace moves beyond stub. Until then, verify stub only.

## Prerequisites

- [ ] 3.4 QA complete ([workspace-qa-3.4.md](workspace-qa-3.4.md), [workspace-qa-cai.md](workspace-qa-cai.md))
- [ ] `pytest agent/tests -q` passes on `Aquila-3.5` branch

## Learn stub (3.4 baseline)

- [x] Learn Mode shows 3.5 placeholder (no task execution)
- [x] No agent worker started from Learn page

## Learn home (M1 — when implemented)

- [ ] Learn Mode opens course home (not stub text only)
- [ ] Course list loads from instance storage
- [ ] Switching instances preserves Learn data per instance

## Course model (M2 — when implemented)

- [ ] Create / open / delete course
- [ ] Assignments visible with status (pending / submitted)

## Tutor agent (M3 — when implemented)

- [ ] Optional “Ask tutor” uses read-only tools
- [ ] No writes outside Learn data directory

## Regression

- [ ] Character AI, Chat, Research, Writing, Code, Task workspaces unchanged
- [ ] `pytest agent/tests -q` passes
