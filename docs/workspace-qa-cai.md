# Workspace QA — Character AI (CAI) Mode

Run after implementation and before tagging 3.4 release (with `docs/workspace-qa-3.4.md`).

## Setup

- [x] Ollama running with configured model
- [x] Fresh or test instance with `default_mode: character` (optional)
- [x] SearXNG running (`docker compose up -d`) when testing **Research lore**

## Home

- [x] Character Mode appears in workspace selector
- [x] Home lists existing personas with tagline / last activity
- [x] **New persona** opens Create view
- [x] **Delete** removes persona folder

## Create

- [x] Name + description required
- [x] Attach PDF/image — build receives attachment context
- [x] **Research lore** — when checked, build uses a **4-step plan** (search → read → synthesize → finalize) and the **search** step allowlist includes `web_search` / `read_webpage`. Test with a **short** description and **no** attachments so step 1 is web research, not auto-ingest skip.
- [x] Build shows execution log; completes with `initialization.md` under `Agent-Instances/{instance}/personas/{id}/` + greeting
- [x] On success, switches to Chat and shows greeting when history empty
- [x] `write_persona_file` accepts only `file_path='initialization.md'` (canonical persona path)

## Chat

- [x] Replies stay in character (no “As an AI…”)
- [x] History persists across reopen (`chat_history.json` per persona)
- [x] **Notes about you** panel saves to `user_preferences.md`
- [x] Attachments on chat messages (text + images) — see `docs/cai-mode.md` for vision model note
- [x] Clear chat view does not wipe saved `chat_history.json` until new messages saved

## Regression

- [x] Chat Mode still uses global history only (`_chat_history_messages`); Character Mode uses per-persona `chat_history.json` (automated: `test_character_chat_isolation.py`)
- [x] Other workspaces unchanged
- [x] `pytest agent/tests -q` passes

## Automated CAI tests

```bash
cd agent && pytest tests/test_character_build_ingest.py tests/test_character_chat.py tests/test_character_chat_isolation.py tests/test_gui_character_worker.py tests/test_gui_character_page.py -q
```
