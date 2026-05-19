#!/usr/bin/env bash
# Start Ollama with TurboQuant KV-cache compression.
# Usage: ./scripts/ollama-serve-turboquant.sh [preset]
# Presets: tq2 tq2k tq3 (default) tq3k tq4 tq4k

set -euo pipefail

PRESET="${1:-tq3}"

export OLLAMA_NEW_ENGINE=1
export OLLAMA_KV_CACHE_TYPE="$PRESET"

case "$PRESET" in
  tq2|tq3|tq4)
    export OLLAMA_FLASH_ATTENTION=1
    ;;
  tq2k|tq3k|tq4k)
    unset OLLAMA_FLASH_ATTENTION 2>/dev/null || true
    ;;
  *)
    echo "Unknown preset: $PRESET" >&2
    exit 1
    ;;
esac

echo "TurboQuant Ollama serve"
echo "  OLLAMA_NEW_ENGINE=$OLLAMA_NEW_ENGINE"
echo "  OLLAMA_KV_CACHE_TYPE=$OLLAMA_KV_CACHE_TYPE"
echo "  OLLAMA_FLASH_ATTENTION=${OLLAMA_FLASH_ATTENTION:-<unset>}"
echo ""
echo "Create models: ollama create aquila-tq-64k -f Modelfile.tq-64k"
echo "Set .env: OLLAMA_MODEL=aquila-tq-64k"
echo ""

exec ollama serve
