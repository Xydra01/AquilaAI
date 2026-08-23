# Data Processing Mode (experimental)

**Superseded in 4.0 by [ML Lab](ml-lab-vision.md).** This doc describes the 3.5 prototype only.

**Status:** Disabled in the GUI by default. Set `AQUILA_ENABLE_DATA_PROCESSING=1` in `.env` and restart Aquila to show the workspace.

## What it does

Data Processing is a **batch ingest** workspace for sorting files from an input folder into labeled output subfolders. It bypasses the standard `LoopEngine` tool loop and runs a dedicated pipeline in [`agent/tasks/data_processor.py`](../agent/tasks/data_processor.py).

| File type | Behavior |
|-----------|----------|
| Images (`.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`) | Classified with [`agent/vision/cnn_classifier.py`](../agent/vision/cnn_classifier.py); copied into CNN-predicted subfolders |
| Other files (CSV, text, etc.) | Per-file Ollama JSON (`action` / `destination_subfolder`) with context wiped between files |

The GUI builds a prompt from input path, output path, and optional rules text ([`agent/gui/gui_pages/data_page.py`](../agent/gui/gui_pages/data_page.py)).

## Requirements

- Trained CNN weights under `models/` (gitignored) — see [vision-and-cnn.md](vision-and-cnn.md)
- Ollama running for non-image files
- Optional env limits in `.env.EXAMPLE`:
  - `AQUILA_DATA_MAX_FILE_MB`
  - `AQUILA_DATA_MAX_CSV_ROWS`

## Enable in GUI

```bash
# .env
AQUILA_ENABLE_DATA_PROCESSING=1
```

When enabled:

- Sidebar shows **Data Processing**
- Home screen shortcut card appears
- `INSTANCE_DEFAULT_MODE_IDS` includes `data`

When disabled (default), `AgentWorker` rejects `mode=data` with a clear message if invoked programmatically.

## Not available on

- Remote Companion PWA (no data-processing endpoint)
- MCP harness scenarios

## Related code

| Path | Role |
|------|------|
| `agent/gui/gui_modes.py` | `data_processing_enabled()` feature flag |
| `agent/gui/gui.py` | Conditional `DataPage` registration; `AgentWorker` branch |
| `agent/tasks/data_processor.py` | Core batch runner |
| `agent/vision/cnn_classifier.py` | Image classification |
