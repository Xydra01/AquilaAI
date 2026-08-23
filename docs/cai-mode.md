# Character AI (CAI) Mode

Character AI is a **per-instance** roleplay workspace in Aquila OS 3.4+. Each Aquila instance keeps its own personas under `Agent-Instances/{instance_id}/personas/`.

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

Build runs `run_unified_task(..., mode="character_build")` on the **capability act path** (`capabilities[]` per turn, not raw tools).

### Without Research lore (3 steps)

1. **read** — `cap.persona.ingest_sources@v1` (ingest description + attachments into scratchpad)
2. **synthesize** — `cap.persona.write_initialization@v1` once for `initialization.md` (≥ ~800 characters)
3. **finalize** — `cap.persona.finalize@v1` (greeting + tagline)

### With Research lore checked (4 steps)

1. **search** — `cap.persona.gather_lore@v1` (web lore into scratchpad; requires SearXNG)
2. **read** — `cap.persona.ingest_sources@v1` (merge attachments if needed)
3. **synthesize** — `cap.persona.write_initialization@v1` once
4. **finalize** — `cap.persona.finalize@v1`

The GUI passes `persona_research_lore=True` into the loop so capability allowlists and plan expansion match the checkbox (not prompt text alone).

Plans attach `capability_id` per step; the act loop validates against allowed capability IDs for each `step_kind`.

**PDF attachments:** Comic/wiki PDFs may log harmless MuPDF font warnings; text extraction still runs when a text layer exists.

Task ledger: `Agent-Tasks/persona_build_{persona_id}.json` (regenerated each build).

## Chat behavior

- Uses `run_character_chat()` with `get_character_prompt()` — **no** `MODES_ROSTER`, **no** tool JSON.
- System prompt includes `initialization.md`, user prefs, and **scene-agency rules** (proactive play, minimal question stacks).
- Temperature defaults to **0.8** — override with `AQUILA_CHARACTER_TEMP` in `.env` (see `.env.EXAMPLE`).
- Global GUI chat history (`_chat_history_messages`) is **not** used; only `chat_history.json` for the active persona.
- **Attachments:** text chunks are appended to the user message and saved in history; **images** are sent on the current turn only (vision model required — use a multimodal Ollama model if image chat fails).
- Every **10 user turns**, a lightweight call may append bullets to `user_preferences.md`.

## Manual QA

See **[workspace-qa-cai.md](workspace-qa-cai.md)**.
