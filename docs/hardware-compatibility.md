# Hardware compatibility (Aquila 3.5 packaged)

Aquila uses **stock portable Ollama** bundled in the installer. Presets are chosen in the setup wizard and shown under Settings → AI Engine.

## Supported matrix

| Profile | Detection | Inference | Default model | Context |
|---------|-----------|-----------|---------------|---------|
| **NVIDIA high** | ≥12 GB VRAM | CUDA via Ollama | `aquila` | 32768 |
| **NVIDIA mid** | 6–11 GB VRAM | CUDA via Ollama | `aquila` | 16384 |
| **NVIDIA low** | &lt;6 GB VRAM | CUDA via Ollama | **`aquila-lite`** (optional full `aquila`) | 8192 |
| **Apple Silicon** | macOS ARM | Metal via Ollama | `aquila` | 32768 |
| **Intel / AMD** | GPU name heuristics | Ollama backend | `aquila` | 16384 |
| **Snapdragon / Copilot+** | Windows ARM64 | **CPU only** (Oryon NEON) | **`aquila-lite`** (optional full `aquila`) | 8192 |
| **CPU only** | No discrete GPU | CPU | **`aquila-lite`** (optional full `aquila`) | 8192 |

## Default models

| Tag | Base | When |
|-----|------|------|
| **`aquila`** | `qwen3.5:9b` | GPU / Apple Silicon (default) |
| **`aquila-lite`** | `qwen2.5:3b` | CPU-only, Copilot+, and NVIDIA low VRAM (default); ~2 GB download |

Packaged setup pulls the profile default automatically. CPU and low-VRAM GPU users can optionally install full **`aquila`** (~7 GB extra) from the setup wizard.

Optional **`aquila_heretic`** (HauhauCS GGUF) remains GPU-only in the wizard — not auto-selected.

Modelfile variants under `modelfiles/`:

- `Modelfile` — default 32k (full Aquila)
- `Modelfile.lite` — Aquila Lite on `qwen2.5:3b`, 8k context
- `Modelfile.cpu` / `Modelfile.arm` — full Aquila 8k context for CPU / Copilot+
- `Modelfile.low-vram` — full Aquila 8k context for optional install on low-VRAM NVIDIA
- `Modelfile.Heretic` — optional advanced

## Snapdragon / Adreno X1-85 / Hexagon NPU

Copilot+ PCs include **Adreno GPU** and **Hexagon NPU**, but **stock Ollama on Windows ARM64 does not use them** today. Aquila runs on the **CPU** (~5–20 tok/s for 8B-class models, workload-dependent).

llama.cpp has experimental Adreno OpenCL support; it is **not** part of the bundled Ollama build in 3.5. NPU offload is tracked upstream ([llama.cpp#7772](https://github.com/ggml-org/llama.cpp/issues/7772)).

**4.0:** optional second engine URL if Ollama or compatible runtimes add stable NPU/GPU paths.

## TurboQuant

Long-context TurboQuant (`aquila-tq-*` on port 11435) requires a **custom NVIDIA CUDA build** — **developer install only** in 3.5, not the packaged MVP.

## Multi-GPU

Single GPU / one Ollama engine at a time (VRAM policy). Multi-worker scheduling is planned for 5.0.
