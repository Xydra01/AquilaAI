# Aquila 3.4 — Workspace QA checklist

Run before tagging 3.4 workspace-complete or starting 3.5 (Learn mode).

## Prerequisites

- [x] `pip install -r requirements.txt`
- [x] Ollama running with `aquila` model
- [x] `docker compose up -d` (SearXNG on port 8080)
- [x] `pytest agent/tests -q` passes

## Chat workspace

- [x] Open instance → Chat Mode
- [x] Send message; streaming renders markdown on finish
- [x] Attach file; chunk appears in next message context (chat injects `text_chunks`; UI shows attachment notice under your message)
- [x] Stop mid-run; UI recovers
- [x] Clear chat view preserves history for next turn

## Research workspace

- [x] SearXNG search returns results in Results tab
- [x] Double-click result opens Reader tab
- [x] Journal Save persists under `Agent-Research/.journal/{instance}.md`
- [x] “Include in next run” + research task sees notes in execution log / behavior
- [x] Plan tracker tab updates during research run

## Writing workspace

- [x] Home lists `Agent-Drafts/*.md`
- [x] Open in canvas loads markdown; Preview tab updates
- [x] Sync to draft buffer writes `active_draft_state.json`
- [x] Highlight + “Edit selection (chat)” returns revised text
- [x] New / Edit with agent starts writing-mode task

## Task workspace (Autonomous)

- [x] Plan column shows step list with status icons
- [x] Execution log and state tracker update during run
- [x] Resume task dialog works for in-progress ledgers

## Code workspace

- [x] Open in-place or Import sandbox
- [x] Editor tabs are editable (not read-only)
- [x] File tree click switches tab
- [x] Save buffer updates `active_code_state.json`
- [x] Sync to disk writes files
- [x] Accept/Reject pending patches; warning if user edited same file

## Learn stub

- [x] Learn Mode shows 3.5 placeholder (no task execution)

## Global

- [x] Dark/light theme applies to all workspaces
- [x] Mode switch shows correct dedicated layout per mode
