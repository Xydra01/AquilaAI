# Vision and CNN (local artifacts)

Aquila includes **integrated** vision code under [`agent/vision/`](../agent/vision/) for experimental Data Processing mode. **Training tooling and weights stay local** and are not pushed to GitHub.

## What is in the repository

| Path | Purpose |
|------|---------|
| `agent/vision/cnn_classifier.py` | Runtime classifier used by Data Processing |
| `agent/vision/train_cnn.py` | Train ResNet-style classifier; output to `models/` |
| `agent/vision/evaluate_cnn.py` | Evaluation helpers |
| `agent/vision/fast_sorter.py` | Batch sort utility |
| `agent/vision/biomed_classifier.py` | BioCLIP-related helpers |

## What stays local (`.gitignore`)

| Path | Purpose |
|------|---------|
| `standalone_cnn_toolkit/` | Standalone training/sorting scripts (duplicate of integrated tooling for offline experiments) |
| `overnight_pipeline_manager.py` | Local orchestrator for overnight train → pseudo-label → finetune |
| `models/` | Deployed weights + `cnn_classes.json` |
| `*.pth` | Any PyTorch checkpoint anywhere in the tree |

## Workflow

1. Train locally with `agent/vision/train_cnn.py` or scripts in `standalone_cnn_toolkit/`
2. Place production weights in `models/custom_diatom_resnet.pth` and class map in `models/cnn_classes.json`
3. Enable Data Processing if needed: `AQUILA_ENABLE_DATA_PROCESSING=1` — see [data-processing-mode.md](data-processing-mode.md)

Environment overrides (optional):

- `CNN_MODEL_PATH`
- `CNN_CLASSES_PATH`

## Why two code trees?

- **`agent/vision/`** — integrated with Aquila OS; tracked in Git
- **`standalone_cnn_toolkit/`** — self-contained Tkinter/batch toolkit for long local training runs; **not** part of the shipped product

They do not import each other. Copy trained artifacts into `models/` for the integrated path.
