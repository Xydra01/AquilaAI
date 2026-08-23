#!/usr/bin/env bash
# Portable Ollama on 11435 WITHOUT TurboQuant (works before a TQ build is ready).
# Aquila: OLLAMA_BASE_URL=http://127.0.0.1:11435  OLLAMA_MODEL=aquila-tq-64k
# For TurboQuant: ./scripts/ollama-serve-turboquant-port.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

OLLAMA_BIN_RESOLVED="$(aq_require_ollama ollama-turboquant)"
export PATH="$(dirname "$OLLAMA_BIN_RESOLVED"):$PATH"

unset OLLAMA_KV_CACHE_TYPE OLLAMA_NEW_ENGINE OLLAMA_FLASH_ATTENTION 2>/dev/null || true
export OLLAMA_HOST="127.0.0.1:11435"
echo "Portable Ollama serve (no TurboQuant) on $OLLAMA_HOST"
echo "  Binary: $OLLAMA_BIN_RESOLVED"
exec "$OLLAMA_BIN_RESOLVED" serve
