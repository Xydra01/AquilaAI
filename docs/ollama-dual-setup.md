# Dual Ollama: stock (default) + TurboQuant (optional)

Aquila uses **two portable Ollama installs** so you can run community GGUFs (HauhauCS, etc.) on modern stock Ollama and switch to **TurboQuant** only when you need long-context `aquila-tq-*` models.

| Port | Script | Binary | Use for |
|------|--------|--------|---------|
| **11434** | `.\scripts\ollama-serve-stock.ps1` | `tools\ollama-stock\` (v0.30+ rc) | **Default** — `aquila`, `aquila_heretic`, HauhauCS, HF GGUFs |
| **11435** | `.\scripts\ollama-serve-turboquant-port.ps1` | `tools\ollama-turboquant\` (PR #15505) | `aquila-tq-32k` / `64k` / `96k` when VRAM/context matter |

Quit the **system tray Ollama** (old 0.24.x) before starting stock on 11434 — it cannot load Qwen 3.5 (`unknown model architecture: qwen35`).

## One-time setup

```powershell
cd F:\Users\myfri\agent-projects

# Stock Ollama (Qwen 3.5 + HauhauCS)
.\scripts\install-ollama-stock.ps1

# Terminal 1 — leave running
.\scripts\ollama-serve-stock.ps1

# Terminal 2 — pull + tag heretic persona
.\scripts\ollama-create-heretic.ps1
```

`.env` for daily use (HauhauCS via `aquila_heretic`):

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=aquila_heretic
```

## Switch to TurboQuant

Terminal 1 (optional, leave running):

```powershell
.\scripts\ollama-serve-turboquant-port.ps1
```

`.env`:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11435
OLLAMA_MODEL=aquila-tq-64k
```

Create TQ models once: `.\scripts\ollama-create-tq-models.ps1` (with `OLLAMA_HOST=http://127.0.0.1:11435`).

## CLI on the right server

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11434"   # stock
.\tools\ollama-stock\ollama.exe list

$env:OLLAMA_HOST = "http://127.0.0.1:11435"   # turboquant
.\tools\ollama-turboquant\ollama.exe list
```

Both share `~\.ollama\models` — blobs are not duplicated per port.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `unknown model architecture: qwen35` | Tray Ollama is 0.24 — quit tray, use `ollama-serve-stock.ps1` |
| Port already in use | `netstat -ano \| findstr 11434` — stop conflicting `ollama.exe` |
| HauhauCS fails on TQ (11435) | Expected — use stock (11434) for HauhauCS |
| `aquila_heretic` missing | `.\scripts\ollama-create-heretic.ps1` |

See also [ollama-turboquant.md](ollama-turboquant.md).
