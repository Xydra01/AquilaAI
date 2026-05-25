# Local Ollama binaries

Portable installs only — not committed to git.

| Path | Install | Port | Purpose |
|------|---------|------|---------|
| `ollama-stock/` | `.\scripts\install-ollama-stock.ps1` | **11434** | **Default** — Qwen 3.5, HauhauCS, `aquila_heretic` |
| `ollama-turboquant/` | `.\scripts\install-ollama-turboquant-pr.ps1` | **11435** | Optional TurboQuant — `aquila-tq-*` |

**Start servers**

```powershell
.\scripts\ollama-serve-stock.ps1              # 11434
.\scripts\ollama-serve-turboquant-port.ps1    # 11435
```

Quit **system tray Ollama** (0.24.x) before using 11434.

Models live in `%USERPROFILE%\.ollama\models` (shared by both servers).

See [docs/ollama-dual-setup.md](../docs/ollama-dual-setup.md).
