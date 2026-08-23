# Qwopus Coder (`aquila_qwopus`) for Aquila

**Qwopus3.5-9B-Coder** is a Qwen 3.5 9B derivative tuned for agentic coding, tool calling, and structured reasoning. Aquila exposes it as the tag **`aquila_qwopus`** — the recommended default on GPU hardware profiles. Stock **`aquila`** (plain `qwen3.5:9b`) remains available as a stable fallback.

## Why Qwopus vs stock `aquila` vs `aquila_heretic`

| Model | Base | Best for |
|-------|------|----------|
| **`aquila_qwopus`** | [Jackrong Qwopus Coder GGUF](https://huggingface.co/Jackrong/Qwopus3.5-9B-Coder-GGUF) | Tasks, coding, tool loops, fewer retries — native Qwen thinking |
| **`aquila`** | `qwen3.5:9b` | Stable fallback, packaged baseline, maximum compatibility |
| **`aquila_heretic`** | HauhauCS uncensored Qwen 3.5 | Advanced / less-filtered persona (optional) |

## Why MTP was dropped

The repo previously included `Modelfile.aquila-qwopus-mtp` pointing at a **Multi-Token Prediction (MTP)** GGUF. MTP weights are a speculative **draft head**, not a primary inference model on stock Ollama. Aquila does not wire draft+main pairing today. Use the **standard Coder GGUF** only.

## One-time install

Requires stock Ollama on port **11434** (see [ollama-dual-setup.md](ollama-dual-setup.md)).

```bash
./scripts/install-ollama-stock.sh
./scripts/ollama-serve-stock.sh          # terminal 1
./scripts/ollama-create-qwopus.sh        # terminal 2
```

Windows PowerShell shim: `./scripts/ollama-create-qwopus.ps1`

Modelfile: [`modelfiles/Modelfile.Qwopus`](../modelfiles/Modelfile.Qwopus) — minimal `FROM` + parameters only (no custom `TEMPLATE`) so Ollama applies the Qwen 3.5 renderer for native `message.thinking`.

## Daily `.env`

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=aquila_qwopus
AQUILA_ENABLE_THINK=1
AQUILA_ACT_TWO_PHASE=1
```

Stock fallback:

```env
# OLLAMA_MODEL=aquila
```

You can also pick the model in **Settings → Ollama** without editing `.env` ([runtime-settings.md](runtime-settings.md)).

## First-run wizard (packaged install)

On GPU profiles, the setup wizard installs **`aquila_qwopus`** as the primary model. Optional checkboxes:

- **Stock aquila** (`qwen3.5:9b` fallback)
- **aquila_heretic** (advanced)

CPU / lite profiles still use **`aquila-lite`** (`qwen2.5:3b`).

## Surfaces

Qwopus works across Aquila surfaces that use the configured `OLLAMA_MODEL`:

- Chat (threads, thinking pane)
- Tasks / act loop (two-phase think → tool JSON)
- Plan, explore, character, learn
- Remote companion and bounded-tools chat

**Not recommended:** TurboQuant extended-context path (`aquila-tq-*`) with Qwopus — untested; use stock `aquila` or TQ models on port 11435 instead.

## Health check / live tests

```bash
./scripts/aquila-health-check.sh qwopus
```

Or manually:

```bash
cd agent
OLLAMA_MODEL=aquila_qwopus python -m pytest tests/test_live_qwopus_tools.py -m qwopus -v
```

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Thinking pane empty | Recreate from [`modelfiles/Modelfile.Qwopus`](../modelfiles/Modelfile.Qwopus) — do **not** add a hand-rolled ChatML `TEMPLATE` |
| HTTP 400 `does not support thinking` | Confirm tag is `aquila_qwopus`; set `AQUILA_ENABLE_THINK=1` |
| Act loop JSON parse failures | Keep `AQUILA_ACT_TWO_PHASE=1` (think pass, then schema act pass) — see [thinking.md](thinking.md) |
| `aquila_qwopus` missing in Settings | Run `./scripts/ollama-create-qwopus.sh` |
| Slow learn archive | Set `AQUILA_LEARN_ARCHIVE_GENERATION_CAP` or disable thinking for archive-only — [thinking.md](thinking.md) |

## See also

- [thinking.md](thinking.md) — native `message.thinking` vs JSON `reasoning`
- [structured-output.md](structured-output.md) — tool JSON schemas
- [ollama-dual-setup.md](ollama-dual-setup.md) — stock vs TurboQuant ports
