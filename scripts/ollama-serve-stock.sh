#!/usr/bin/env bash
# Stock Ollama on port 11434 (default Aquila path).
# Install first: ./scripts/install-ollama-stock.sh
# TurboQuant (optional): ./scripts/ollama-serve-turboquant-port.sh  -> 11435

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PORT="11434"
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

STOCK_BIN="$(aq_find_ollama ollama-stock || true)"
if [ -z "$STOCK_BIN" ]; then
  echo "Stock ollama not found - running install..."
  "$AQ_SCRIPTS_DIR/install-ollama-stock.sh"
  STOCK_BIN="$(aq_require_ollama ollama-stock)"
fi
BIN_DIR="$(dirname "$STOCK_BIN")"
if command -v cygpath >/dev/null 2>&1; then
  BIN_DIR="$(cygpath -u "$BIN_DIR")"
fi
export PATH="$BIN_DIR:$PATH"

# Stock must not inherit TurboQuant's custom engine / tq-presets.
unset OLLAMA_NEW_ENGINE 2>/dev/null || true

# Keep the FULL context window resident in VRAM. Flash attention + a quantized
# KV cache shrink the KV cache (q8_0 ~= half, q4_0 ~= quarter of fp16), which is
# what lets a 32k window stay 100% on the GPU instead of spilling layers to CPU
# (the dreaded ~3 tok/s). q8_0 is effectively lossless.
#   Disable:   OLLAMA_FLASH_ATTENTION=0 OLLAMA_KV_CACHE_TYPE=f16 ./scripts/ollama-serve-stock.sh
#   Tighter:   OLLAMA_KV_CACHE_TYPE=q4_0 ./scripts/ollama-serve-stock.sh
export OLLAMA_FLASH_ATTENTION="${OLLAMA_FLASH_ATTENTION:-1}"
KV="${OLLAMA_KV_CACHE_TYPE:-q8_0}"
case "$KV" in
  tq*) KV="q8_0" ;;            # TurboQuant presets are invalid on stock Ollama
esac
# Quantized KV requires flash attention; fall back to f16 if FA was disabled.
case "$OLLAMA_FLASH_ATTENTION" in
  0|false|off|no|"") OLLAMA_FLASH_ATTENTION=0; KV="f16" ;;
esac
export OLLAMA_KV_CACHE_TYPE="$KV"

export OLLAMA_HOST="127.0.0.1:$PORT"
echo "Stock Ollama serve on $OLLAMA_HOST"
echo "  Binary                 : $STOCK_BIN"
echo "  OLLAMA_FLASH_ATTENTION : $OLLAMA_FLASH_ATTENTION"
echo "  OLLAMA_KV_CACHE_TYPE   : $OLLAMA_KV_CACHE_TYPE"
"$STOCK_BIN" --version || true
echo ""
echo "Aquila .env: OLLAMA_BASE_URL=http://127.0.0.1:$PORT"
echo "Verify she is 100% on GPU:  ollama ps   (look for '100% GPU')"
echo "TurboQuant (other terminal): ./scripts/ollama-serve-turboquant-port.sh"
echo ""
exec "$STOCK_BIN" serve
