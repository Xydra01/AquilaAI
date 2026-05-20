# Local Ollama / TurboQuant artifacts

This folder holds **local-only** binaries and build outputs. Nothing here is committed to git.

## Keep (required for TurboQuant)

| Path | Purpose |
|------|---------|
| `ollama-turboquant/` | Portable Ollama built from [PR #15505](https://github.com/ollama/ollama/pull/15505). Install: `.\scripts\install-ollama-turboquant-pr.ps1` |

## Optional (rebuild only)

| Path | Purpose |
|------|---------|
| `ollama-pr15505/` | PR source tree after `install-ollama-turboquant-pr.ps1` (large). Safe to delete if you will not rebuild; the install script re-downloads. |

## Safe to delete

These were intermediate installs or logs from setup — remove anytime to reclaim disk space:

- `ollama-v0.30.0-rc17/` — stock rc17 zip (TQ does not work on Windows)
- `ollama-tq/` — old experimental copy
- `pr15505-build.log`, `pr15505-cuda-rebuild.log` — build logs

## Models (in `~/.ollama/models`, not here)

Create from repo root with TurboQuant serve on port 11435:

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11435"
.\scripts\ollama-create-tq-models.ps1
```

See [docs/ollama-turboquant.md](../docs/ollama-turboquant.md).
