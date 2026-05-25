# Character AI (CAI) Mode

Character AI is a **per-instance** roleplay workspace in Aquila OS 3.4. Each Aquila instance keeps its own personas under `Agent-Instances/{instance_id}/personas/`.

## Workspace overview

1. **Home** — list personas; open chat, create new, or delete.
2. **Create** — name, description, optional file/image attachments, optional **Research lore on the web**, then **Build persona** (agent loop).
3. **Chat** — in-character streaming conversation with per-persona history and editable **Notes about you**.

Select **Character Mode** from the workspace dropdown (or set `default_mode: character` when creating an instance).

## Persona files

Each persona lives in:

```
Agent-Instances/{instance_id}/personas/{persona_id}/
  persona.json          # metadata (name, tagline, greeting, flags)
  initialization.md     # character bible (injected into system prompt)
  user_preferences.md   # what the character remembers about you
  chat_history.json     # last N turns (not merged into global chat history)
  sources/              # optional attachment storage during build
```

## What drives in-character behavior

| Source | Used in chat? |
|--------|----------------|
| `initialization.md` | Yes — full text in system prompt (CHARACTER BIBLE) |
| `user_preferences.md` | Yes — WHAT YOU REMEMBER ABOUT THE USER |
| `persona.json` → `display_name` | Yes — “You are {name}…” |
| `persona.json` → `greeting` | UI only (first bubble when history empty) |
| `persona.json` → `description` | Build input / metadata only |

## Build pipeline

Build runs `run_unified_task(..., mode="character_build")`.

### Without Research lore (3 steps)

1. **read** — `save_research_note` only (ingest description + attachments)
2. **synthesize** — `write_persona_file` **once** for `initialization.md` (≥ ~800 characters)
3. **finalize** — `finalize_persona`, then `finish_task`

### With Research lore checked (4 steps)

1. **search** — `web_search`, `read_webpage`, `save_research_note` (requires SearXNG)
2. **read** — merge attachments via `save_research_note` if needed
3. **synthesize** — `write_persona_file` once
4. **finalize** — `finalize_persona`

The GUI passes `persona_research_lore=True` into the loop so tool allowlists and plan expansion match the checkbox (not prompt text alone).

`write_persona_file` only accepts `file_path='initialization.md'` and always writes to `Agent-Instances/{instance}/personas/{id}/initialization.md`.

Task ledger: `Agent-Tasks/persona_build_{persona_id}.json` (regenerated each build).

**PDF attachments:** Comic/wiki PDFs may log harmless MuPDF font warnings; text extraction still runs when a text layer exists.

## Chat behavior

- Uses `run_character_chat()` with `get_character_prompt()` — **no** `MODES_ROSTER`, **no** tool JSON.
- System prompt includes `initialization.md`, user prefs, and **scene-agency rules** (proactive play, minimal question stacks).
- Temperature defaults to **0.8** — override with `AQUILA_CHARACTER_TEMP` in `.env` (see `.env.EXAMPLE`).
- Global GUI chat history (`_chat_history_messages`) is **not** used; only `chat_history.json` for the active persona.
- **Attachments:** text chunks are appended to the user message and saved in history; **images** are sent on the current turn only (vision model required — use a multimodal Ollama model if image chat fails).
- Every **10 user turns**, a lightweight call may append bullets to `user_preferences.md`.

## Manual QA

See **[workspace-qa-cai.md](workspace-qa-cai.md)**.
