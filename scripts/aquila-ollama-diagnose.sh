#!/usr/bin/env bash
# Aquila Ollama diagnostics - TTFT/tokens/s + optional GPU/VRAM sampling.
#
# Usage (repo root):
#   ./scripts/aquila-ollama-diagnose.sh [--trials N] [--prompt TEXT] [--warmup]
#       [--eject-between-trials] [--no-gpu-sampling] [--no-process-sampling]
#       [--gpu-interval-s F] [--proc-interval-s F] [--json-path PATH]

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TRIALS=1
PROMPT="pong"
GPU_INTERVAL="0.75"
PROC_INTERVAL="0.75"
JSON_PATH=""
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    --trials) TRIALS="$2"; shift 2 ;;
    --prompt) PROMPT="$2"; shift 2 ;;
    --gpu-interval-s) GPU_INTERVAL="$2"; shift 2 ;;
    --proc-interval-s) PROC_INTERVAL="$2"; shift 2 ;;
    --json-path) JSON_PATH="$2"; shift 2 ;;
    --warmup) EXTRA+=("--warmup-before-trials"); shift ;;
    --eject-between-trials) EXTRA+=("--eject-between-trials"); shift ;;
    --no-gpu-sampling) EXTRA+=("--no-gpu-sampling"); shift ;;
    --no-process-sampling) EXTRA+=("--no-process-sampling"); shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

PY="$(aq_python)"
OUT_DIR="$AQ_REPO_ROOT/Agent-Logs/diagnostics"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
[ -z "$JSON_PATH" ] && JSON_PATH="$OUT_DIR/ollama_diagnostics_${TS}.json"

cd "$AQ_REPO_ROOT/agent"
"$PY" -m ollama_diagnostics \
  --trials "$TRIALS" \
  --prompt "$PROMPT" \
  --json-path "$JSON_PATH" \
  --gpu-interval-s "$GPU_INTERVAL" \
  --proc-interval-s "$PROC_INTERVAL" \
  "${EXTRA[@]}"

echo ""
echo "Diagnostics JSON written to: $JSON_PATH"
