#!/usr/bin/env bash
# Start Ollama with TurboQuant KV-cache compression.
# Usage: ./scripts/ollama-serve-turboquant.sh [preset] [--port N]
# Presets: tq2 tq2k tq3 tq3k tq4 (default) tq4k
#
# Prefers the portable TurboQuant build in tools/ollama-turboquant if present.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PRESET="${AQUILA_TQ_PRESET:-tq4}"
PORT="11434"
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --preset) PRESET="$2"; shift 2 ;;
    tq2|tq2k|tq3|tq3k|tq4|tq4k) PRESET="$1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

OLLAMA_BIN_RESOLVED="$(aq_require_ollama ollama-turboquant)"
# Make sure sibling libs (lib/ollama) resolve by prepending the binary dir to PATH.
BIN_DIR="$(dirname "$OLLAMA_BIN_RESOLVED")"
if command -v cygpath >/dev/null 2>&1; then
  BIN_DIR="$(cygpath -u "$BIN_DIR")"
fi
export PATH="$BIN_DIR:$PATH"

export OLLAMA_NEW_ENGINE=1
export OLLAMA_KV_CACHE_TYPE="$PRESET"
case "$PRESET" in
  tq2|tq3|tq4)
    export OLLAMA_FLASH_ATTENTION=1
    ;;
  tq2k|tq3k|tq4k)
    unset OLLAMA_FLASH_ATTENTION 2>/dev/null || true
    ;;
esac

export OLLAMA_HOST="127.0.0.1:$PORT"

echo "TurboQuant Ollama serve"
echo "  Binary                 = $OLLAMA_BIN_RESOLVED"
echo "  OLLAMA_HOST            = $OLLAMA_HOST"
echo "  OLLAMA_NEW_ENGINE      = $OLLAMA_NEW_ENGINE"
echo "  OLLAMA_KV_CACHE_TYPE   = $OLLAMA_KV_CACHE_TYPE"
echo "  OLLAMA_FLASH_ATTENTION = ${OLLAMA_FLASH_ATTENTION:-<unset>}"
echo ""
echo "Create TurboQuant models (once, other terminal): ./scripts/ollama-create-tq-models.sh"
echo "Set in .env: OLLAMA_BASE_URL=http://127.0.0.1:$PORT  OLLAMA_MODEL=aquila-tq-32k|64k|96k"
echo ""

exec "$OLLAMA_BIN_RESOLVED" serve
