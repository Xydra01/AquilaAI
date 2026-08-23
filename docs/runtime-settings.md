# Runtime settings (in-app)

Aquila configures **Ollama engines**, **aquila models**, **SearXNG**, and **AQUILA_* tuning** from the desktop GUI or Remote Companion PWA.

## Source of truth

User-facing settings persist to **`Agent-Instances/app_settings.json`** (under your data root) in a `preferences` object keyed by env name (`AQUILA_*`, `OLLAMA_*`, `SEARXNG_*`, `SMTP_*`, …).

At startup and on save, Aquila hydrates `os.environ` from merged **catalog defaults + saved preferences**, so existing code paths that read `os.getenv("AQUILA_*")` keep working without a large refactor.

### Optional `.env` export

When you save from Settings, the **“Also update .env for shell scripts”** checkbox (default **on**) writes exportable keys back to `.env` for CLI scripts and headless runs. Turn it off if you want JSON-only persistence.

On first launch after upgrade, if `preferences` is empty but `.env` exists, catalog keys are imported once into `app_settings.json`.

The catalog lives in `agent/storage/config_catalog.py`; `.env.EXAMPLE` is generated from it.

## Desktop GUI

Open **Settings** from the top bar (next to Home). Use the **Search settings** box to filter by label or `AQUILA_*` key.

### Tier 1 (default)

| Section | Purpose |
|---------|---------|
| **Get Started** | Health checklist (Ollama, model, Docker) |
| **Chat & light research** | URL detection/fetch limits, search caps, scrape char limits |
| **Chat & light coding** | Repo snapshot token budget for Light coding |
| **Thinking & chat** | Native thinking, chat token limits, repeat penalty |
| **Tasks & act loop** | Tool loop, planning, stall limits |
| **Learn & character** | Temperatures and RAG limits |
| **Context & scraping** | Auto-scrape, context tier, tool output caps |
| **AI Engine** | Start/stop Ollama, model picker, `num_ctx` |
| **Web Search** | SearXNG URL, Docker container |
| **Email** | SMTP for `send_email` tool |
| **Integrations** | MCP server JSON |

### Tier 2 (advanced)

Catalog sections marked advanced (Dynamic loop, Structured output, Ollama warmup, Stream guard, Instances & tools, Logging) appear in the nav after Tier 1 pages.

| Section | Purpose |
|---------|---------|
| **Logs** | Engine stdout/stderr |

Packaged installs: see [packaged-install.md](packaged-install.md).

### Chat & light research knobs

| GUI label | Key | Notes |
|-----------|-----|-------|
| Max URLs detected per message | `AQUILA_LIGHT_RESEARCH_MAX_USER_URLS` | Extraction cap from your message text |
| Max pasted URLs to fetch | `AQUILA_LIGHT_RESEARCH_USER_URL_READS` | How many links are actually downloaded |
| Max web searches per message | `AQUILA_LIGHT_RESEARCH_MAX_SEARCHES` | |
| Max words per search query | `AQUILA_LIGHT_RESEARCH_MAX_QUERY_WORDS` | |
| Auto-scrape URLs from search results | `AQUILA_LIGHT_RESEARCH_MAX_URLS` | Not the same as pasted user links |
| Scrape / read character caps | `AQUILA_LIGHT_RESEARCH_SCRAPE_CHAR_CAP`, `READ_MAX_CHARS` | |

### Ollama engines

- **Stock** — `http://127.0.0.1:11434` (portable stock Ollama)
- **TurboQuant** — `http://127.0.0.1:11435` (TurboQuant build)

Each card supports **Start/Stop**, **Use engine**, **Warm up**, **Eject**, and **Logs** (same behavior as the Remote PWA). Only one engine should run at a time (VRAM policy).

After **Start**, the active engine and a sensible aquila model are saved automatically. Use **Apply model** to pick a different tag.

The model dropdown lists only Ollama tags whose name contains `aquila` (case-insensitive).

The top bar shows: `Instance: … | model @ host:port`.

### SearXNG

- Configure **Base URL** and **Engines** (comma-separated SearXNG engine list).
- **Test connection** — probes JSON search.
- **Start/Stop container** — runs `docker compose up -d aquila-search` / `stop` on the repo `docker-compose.yml`.

Deeper index tuning remains in `searxng-settings.yml` at the repo root.

## Remote Companion (PWA)

On the **Servers** tab:

- Engine cards include an **aquila model** dropdown and **Use for chat**.
- After **Start**, you are prompted to retarget chat/tasks to that engine (`POST /api/ollama/active`).
- **SearXNG** section: status, start/stop container, test.

### API (authenticated)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/runtime/settings` | Read active Ollama/SearXNG config |
| PUT | `/api/runtime/settings` | Update and apply to shared client |
| GET | `/api/runtime/env_sections` | Catalog sections + current preference values |
| POST | `/api/runtime/env` | Update preferences (optional `.env` export) |
| GET | `/api/ollama/models?engine=tq\|stock` | List aquila models |
| POST | `/api/ollama/active` | `{ "engine": "tq", "model": "optional" }` |
| GET | `/api/search/status` | Health + Docker status |
| POST | `/api/search/start` / `stop` | Docker compose control |

## Per-instance overrides

When creating an instance on the Home screen, optional **Model override** sets `profile.json` → `ollama_model`. Leave as “use global default” to follow Settings.

## Environment variables (optional / export)

`app_settings.json` overrides catalog defaults once saved from the app. `.env` is optional and can be kept in sync on save:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=aquila_qwopus
SEARXNG_BASE_URL=http://127.0.0.1:8080
SEARXNG_ENGINES=google,bing,duckduckgo,wikipedia
AQUILA_LIGHT_RESEARCH_MAX_USER_URLS=3
AQUILA_LIGHT_RESEARCH_USER_URL_READS=2
```

See `.env.EXAMPLE` for the full generated list.

## Related docs

- [ollama-dual-setup.md](ollama-dual-setup.md) — installing Stock + TurboQuant binaries
- [remote-companion.md](remote-companion.md) — pairing and PWA usage
