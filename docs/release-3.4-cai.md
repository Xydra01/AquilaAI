# Aquila 3.4 — Character AI release notes

## Character AI workspace

- Per-instance personas under `Agent-Instances/{id}/personas/`
- Create flow: attachments, optional **Research lore** (4-step web search plan), `initialization.md` + `finalize_persona`
- In-character chat with per-persona `chat_history.json` (isolated from global Chat Mode history)
- Scene-agency system prompt rules (proactive roleplay, avoid assistant-style Q&A loops)
- `AQUILA_CHARACTER_TEMP` env override (default 0.8)

## Build reliability fixes

- Strict per-step tool allowlists for `character_build` (no `write_file` / `replace_in_file` on synthesize)
- Auto-ingest attachment chunks to scratchpad; optional web search step when Research lore enabled
- `write_persona_file` path hardening (only `initialization.md`, canonical persona directory)
- Multi-chunk `save_research_note` for large PDF ingests

## Tests

- `test_character_build_ingest.py`, `test_character_chat.py`, `test_character_chat_isolation.py`, `test_gui_character_worker.py`, `test_gui_character_page.py`

## Docs

- [cai-mode.md](cai-mode.md), [workspace-qa-cai.md](workspace-qa-cai.md)

## Next

- [roadmap-3.5.md](roadmap-3.5.md) — Learn mode (classroom UI)
