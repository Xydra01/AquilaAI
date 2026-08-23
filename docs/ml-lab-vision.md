# ML Lab vision (Aquila 4.0)

**Status:** Draft — planning document only.

**User-facing name:** **ML Lab** (replaces “Data Processing” and the working title “ML Workbench”).

**Install:** `pip install aquila[ml]` — not required for core Aquila.

## Origin

**Data Processing mode** ([data-processing-mode.md](data-processing-mode.md)) was built quickly to support an internship: batch-sort images with a custom CNN and LLM fallback for non-images. It is **disabled by default** until ML Lab ships.

**4.0 vision:** **ML Lab** — a plan-driven workspace for **training, testing, deploying, and operating** small neural networks (image CNNs first; audio and tabular later).

## User story

> “Here is a folder of labeled images. Workshop the approach with me, run training overnight, show me accuracy, and when I approve, use the model to sort new files.”

Aquila orchestrates the steps; users should not need `standalone_cnn_toolkit/` unless they want low-level scripts.

## Design principles

1. **LLM plans; Python trains** — training loops are tools, not ad-hoc torch in chat.
2. **Ledger-backed** — ML projects use `Agent-Tasks/` / `Agent-Plans/` JSON like other modes.
3. **Artifacts are explicit** — weights in `models/`, metrics under `Agent-Instances/{id}/ml/{project}/`.
4. **Optional extra** — `aquila[ml]` installs torch and ML Lab UI; core install stays lean.
5. **Reuse internship code** — promote `data_processor.py`, `train_cnn.py` patterns into `agent/tool_library/ml_tools.py`.

## Workflow phases

```mermaid
flowchart LR
    Ingest[Ingest_and_validate] --> Plan[Plan_architecture]
    Plan --> Train[Train]
    Train --> Eval[Evaluate]
    Eval --> Deploy[Deploy_to_models]
    Deploy --> Operate[Batch_inference]
```

| Phase | Tool examples | Output |
|-------|---------------|--------|
| **Ingest** | `ml_inspect_dataset`, `ml_split_train_val` | Manifest JSON |
| **Plan** | Planner + user approval | `plan.json` |
| **Train** | `ml_train_classifier` | Checkpoints, logs |
| **Evaluate** | `ml_evaluate_classifier` | Metrics, confusion matrix |
| **Deploy** | `ml_register_model` | `models/{name}.pth` + manifest |
| **Operate** | `ml_batch_classify` | Sorted output (today’s sort pipeline) |

## Migration from Data Processing

| Today (3.5) | ML Lab (4.0) |
|-------------|----------------|
| “Data Processing” sidebar | **ML Lab** workspace |
| `AQUILA_ENABLE_DATA_PROCESSING` | `aquila[ml]` installed + optional env flag |
| `data_page.py` | `ml_lab_page.py` (name TBD in code) |
| Single input → output folder | Full workflow UI + metrics |

3.5 Data Processing remains the hidden prototype until ML Lab replaces it.

## Perception layer

ML Lab **produces** models the **perception layer** consumes (chat attachment tags, etc.). See [roadmap-4.0.md](roadmap-4.0.md) Pillar C.

## MVP checklist (4.0b)

- [ ] `aquila[ml]` extra in `requirements.txt` with documented deps
- [ ] Dataset inspector + ML Lab GUI panel
- [ ] ResNet-18 transfer learning recipe with logged metrics
- [ ] Deploy to `models/` + manifest
- [ ] Batch classify parity with old Data Processing
- [ ] Harness scenario: tiny train → classify fixture image

## Open questions (implementation time)

1. Pseudo-labeling — first-class tool or advanced doc?
2. Labeling UI in Aquila vs external import (CVAT, Label Studio)?
3. Learn Mode crossover (“course on your own dataset”)?

## See also

- [vision-and-cnn.md](vision-and-cnn.md)
- [data-processing-mode.md](data-processing-mode.md)
- [roadmap-4.0.md](roadmap-4.0.md)
