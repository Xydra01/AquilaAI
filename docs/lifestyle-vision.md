# Lifestyle workspace vision (Aquila 4.0+)

**Status:** Draft — planning document only.

**User-facing name:** **Lifestyle** (new major sidebar workspace — calendar, planning, routines).

## Goal

A dedicated GUI home for **time, plans, and personal organization** — not buried in Settings or Learn-only assignment dates.

Users should:

- See **upcoming events** and daily/weekly planning surfaces
- **Import** schedules from other apps (start with `.ics`; grow toward CalDAV / Google)
- Let Aquila **reason over the calendar** in Chat, Task, and Voice (“What’s free Thursday?”)
- Optionally **trigger saved workflows** on schedule ([workflow-editor-vision.md](workflow-editor-vision.md))

## Existing foundation (3.5 codebase)

| Asset | Location | Notes |
|-------|----------|-------|
| Local calendar DB + ICS import | `agent/tool_library/calendar_tools.py` | SQLite `calendar_v4.db`, primitive ICS parser |
| Learn assignment calendar | [roadmap-3.5.md](roadmap-3.5.md) stretch | Course due dates — should **feed Lifestyle**, not duplicate UI |
| Task mode calendar icon | GUI sidebar | Autonomous Task stays separate; Lifestyle is planning-centric |

## Design principles

1. **Local-first calendar of record** — imported events land in Aquila’s DB; external apps are sync sources, not required at runtime.
2. **Import before sync** — ship **ICS file import** and manual export from Apple/Google before OAuth/CalDAV complexity.
3. **LLM reads structured events** — tools return JSON lists; Chat/Task/Voice use the same tools, not ad-hoc parsing in prompts.
4. **Privacy** — calendar data stays under `AQUILA_DATA_ROOT`; no cloud calendar API unless user opts in.

## Import strategy (phased)

| Phase | Method | User action |
|-------|--------|-------------|
| **4.0e MVP** | `.ics` file import | Export from Apple Calendar / Google Calendar → Import in Lifestyle |
| **4.x** | CalDAV read-only sync | URL + app password / token in Settings |
| **4.x+** | Google Calendar OAuth | Optional; document scopes and revoke |
| **Future** | Apple iCloud CalDAV | Same CalDAV stack where possible |

Apple and Google do not share one API — plan for **ICS + CalDAV** first; Google OAuth as an additive connector.

## MVP checklist (4.0e)

- [ ] **Lifestyle** sidebar page (month/week/agenda views — start with agenda list)
- [ ] ICS import UI (file picker + drag-drop) wired to `import_calendar_ics`
- [ ] CRUD tools: list events, add/edit/delete local events
- [ ] Chat tool palette: `list_upcoming_events`, `find_free_blocks` (simple heuristics)
- [ ] Learn due dates visible in Lifestyle (read-only overlay or merged feed — TBD)

## Stretch

- [ ] Planning boards / goals (lightweight, not a full Notion clone)
- [ ] Workflow schedule triggers
- [ ] Voice: “What’s on my calendar tomorrow?”
- [ ] Remote Companion: read-only agenda view

## Non-goals (4.0)

- Replacing Apple Calendar or Google Calendar as the user’s primary mobile app
- Two-way sync conflicts resolution in MVP
- Smart-home automations tied to calendar (see [smart-home-vision.md](smart-home-vision.md))

## See also

- [roadmap-4.0.md](roadmap-4.0.md)
- [workflow-editor-vision.md](workflow-editor-vision.md)
