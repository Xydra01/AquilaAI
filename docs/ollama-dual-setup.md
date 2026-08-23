# Dual Ollama: stock (default) + TurboQuant (optional)

Aquila uses **two portable Ollama installs** so you can run community GGUFs (HauhauCS, etc.) on modern stock Ollama and switch to **TurboQuant** only when you need long-context `aquila-tq-*` models.

| Port | Script | Binary | Use for |
|------|--------|--------|---------|
| **11434** | `./scripts/ollama-serve-stock.sh` | `tools/ollama-stock/` (v0.30+ rc) | **Default** — `aquila_qwopus`, `aquila`, `aquila_heretic`, HF GGUFs |
| **11435** | `./scripts/ollama-serve-turboquant-port.sh` | `tools/ollama-turboquant/` (PR #15505) | `aquila-tq-32k` / `64k` / `96k` when VRAM/context matter |

Quit the **system tray Ollama** (old 0.24.x) before starting stock on 11434 — it cannot load Qwen 3.5 (`unknown model architecture: qwen35`).

## One-time setup

Run these in Git Bash (Windows) or a terminal (macOS/Linux), from the repo root:

```bash
cd /path/to/agent-projects

# Stock Ollama (Qwen 3.5 + HauhauCS)
./scripts/install-ollama-stock.sh

# Terminal 1 — leave running
./scripts/ollama-serve-stock.sh

# Terminal 2 — recommended Qwopus Coder (GPU default)
./scripts/ollama-create-qwopus.sh

# Optional — HauhauCS heretic persona
./scripts/ollama-create-heretic.sh
```

`.env` for daily use (Qwopus Coder — recommended on GPU):

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=aquila_qwopus
```

Stock `aquila` fallback: `OLLAMA_MODEL=aquila` after `ollama create aquila -f Modelfile`. See [ollama-qwopus.md](ollama-qwopus.md).

## Switch to TurboQuant

You can also switch engines and models from **Aquila OS → Settings** or the Remote PWA **Servers** tab without editing `.env` — see [runtime-settings.md](runtime-settings.md).

Terminal 1 (optional, leave running):

```bash
./scripts/ollama-serve-turboquant-port.sh
```

`.env`:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11435
OLLAMA_MODEL=aquila-tq-64k
```

Create TQ models once: `./scripts/ollama-create-tq-models.sh` (with `OLLAMA_HOST=http://127.0.0.1:11435`).

## CLI on the right server

```bash
export OLLAMA_HOST="http://127.0.0.1:11434"   # stock
./tools/ollama-stock/ollama list

export OLLAMA_HOST="http://127.0.0.1:11435"   # turboquant
./tools/ollama-turboquant/ollama list
```

Both share `~\.ollama\models` — blobs are not duplicated per port.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `unknown model architecture: qwen35` | Tray Ollama is 0.24 — quit tray, use `ollama-serve-stock.sh` |
| Port already in use | Windows: `netstat -ano \| findstr 11434`; macOS/Linux: `lsof -i :11434` — stop conflicting `ollama` |
| HauhauCS fails on TQ (11435) | Expected — use stock (11434) for HauhauCS |
| `aquila_qwopus` missing | `./scripts/ollama-create-qwopus.sh` |
| `aquila_heretic` missing | `./scripts/ollama-create-heretic.sh` |

See also [ollama-turboquant.md](ollama-turboquant.md) and [ollama-qwopus.md](ollama-qwopus.md).
