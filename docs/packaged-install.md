# Packaged install (Aquila 3.5 trail)

End-user install path: **installer → first-run wizard → chat**. No Python, Git, or IDE required.

## Artifacts

| File | Platform |
|------|----------|
| `Aquila-3.5.0-setup.exe` | Windows x64 |
| `Aquila-3.5.0-arm64-setup.exe` | Windows ARM64 / Copilot+ |
| `Aquila-3.5.0-mac.dmg` | macOS |

User data is stored outside the install folder:

- Windows: `%LOCALAPPDATA%\Aquila`
- macOS: `~/Library/Application Support/Aquila`

Upgrading: uninstall the old app, install the new build. Your data folder is kept.

## Building (maintainers)

```powershell
# Windows x64
.\packaging\build-windows.ps1

# Windows ARM64 (Snapdragon)
.\packaging\build-windows.ps1 -Arch arm64
```

Both Windows and macOS build scripts print a **step plan with ETA**, per-step elapsed time, and remaining build ETA. Timings are learned into `packaging/.build-timings-windows.json` / `.build-timings-macos.json` (local; ignored by `*.json`).

```bash
# macOS
chmod +x packaging/build-macos.sh
./packaging/build-macos.sh
```

Requires: Python venv, PyInstaller (`requirements-packaging.txt`), Git Bash on Windows for `fetch-ollama.sh`, Inno Setup (`iscc`) for `.exe` installer.

### Preflight (before compiling)

Full PyInstaller + Inno builds take a long time. Catch wizard / Docker / asset bugs in seconds first:

```powershell
.\scripts\packaged-preflight.ps1
# or quick (no pytest):
.\scripts\packaged-preflight.ps1 -Quick
```

Also scan for Unicode that breaks Windows PowerShell 5.1 (smart quotes / em-dashes):

```powershell
.\scripts\check-shell-unicode.ps1
.\scripts\check-shell-unicode.ps1 -Fix   # ASCII-sanitize .ps1/.bat/.cmd/.iss
```

`packaging/build-windows.ps1` runs packaged preflight automatically unless you pass `-SkipPreflight`.

## First run

1. Welcome — data folder (default per OS)
2. Hardware preset — model + context tuned for your GPU/CPU
3. Download `qwen3.5:9b` and create `aquila` (optional `aquila_heretic`)
4. Start bundled Ollama + smoke test
5. Optional SearXNG Docker container

The wizard runs only for **packaged** builds (`sys.frozen`). Dev installs: set `AQUILA_SHOW_SETUP_WIZARD=1` to test.

## Settings (simplified)

- **Get Started** — health checklist
- **AI Engine** — start/stop Ollama, model, context
- **Web Search** — SearXNG (optional)
- **Email** — SMTP for send_email tool
- **Integrations** — MCP JSON
- **Developer settings** — advanced `AQUILA_*` env tuning
- **Logs** — engine output

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Wizard stuck on model download | Check disk space (~6 GB); retry from Settings |
| Ollama won't start | Settings → AI Engine → Start; see Logs |
| Slow on Copilot+ PC | Expected — CPU-only on ARM64 today (see hardware doc) |
| Web search fails | Install Docker Desktop or skip (chat works without it) |

## Developer install

See [README.md](../README.md) for clone + venv + `start.sh`. Packaged and developer paths share the same agent core.
