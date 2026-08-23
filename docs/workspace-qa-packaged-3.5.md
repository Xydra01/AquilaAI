# Workspace QA — Packaged Aquila 3.5

Clean-machine test of the **installer path** (no terminal). See [packaged-install.md](packaged-install.md).

## Prerequisites

- [ ] Built installer or onedir from `packaging/build-windows.ps1` / `build-macos.sh`
- [ ] Clean VM or user profile (no prior Aquila dev checkout)
- [ ] ~10 GB free disk (app + model download)

## Install

- [ ] Installer completes without errors
- [ ] Desktop / Start Menu shortcut launches Aquila
- [ ] No Git Bash / Python prompt required

## First-run wizard

- [ ] Wizard appears on first launch (packaged build)
- [ ] Hardware line matches machine (NVIDIA / Apple / ARM64 / CPU)
- [ ] Model download completes (`aquila` tag)
- [ ] Ollama starts; smoke test passes or shows clear retry message
- [ ] Skip / optional Docker step works
- [ ] Wizard does not reappear after completion

## Settings (Tier 1)

- [ ] **Get Started** shows Ollama + model healthy after wizard
- [ ] **AI Engine** — Start/Stop, model picker, Apply model
- [ ] **Web Search** — save applies without split-brain
- [ ] **Developer settings** — save reloads advanced env vars

## Core smoke (no terminal)

- [ ] Home → Chat Mode → short message streams a reply
- [ ] Learn Mode home opens
- [ ] Settings → Logs shows engine output after Start

## Platform-specific

### Windows x64

- [ ] `Aquila-3.5.0-setup.exe` installs under Program Files or user-local
- [ ] Data under `%LOCALAPPDATA%\Aquila`

### Windows ARM64 (if available)

- [ ] ARM64 installer bundles ARM64 Ollama
- [ ] UI states CPU (ARM64) performance expectations

### macOS

- [ ] DMG or onedir launches; Gatekeeper note documented if unsigned
- [ ] Data under `~/Library/Application Support/Aquila`

## Upgrade

- [ ] Reinstall newer build preserves chat / instance data in data folder

## Automated (dev machine)

Prefer the preflight (includes these tests plus wizard construction):

```powershell
.\scripts\packaged-preflight.ps1
```

Or the pytest subset alone:

- [ ] `pytest agent/tests/test_platform_paths.py agent/tests/test_hardware_profile.py agent/tests/test_model_setup.py agent/tests/test_setup_wizard_search.py -q`
