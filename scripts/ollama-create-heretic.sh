#!/usr/bin/env bash
# Pull HauhauCS base + create aquila_heretic on stock Ollama (default port 11434).
# Requires: ./scripts/ollama-serve-stock.sh running in another terminal.
# Usage: ./scripts/ollama-create-heretic.sh [--port N]

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PORT="11434"
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

MODELFILE="$AQ_REPO_ROOT/Modelfile.Heretic"
BASE_MODEL="hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M"

STOCK_BIN="$(aq_find_ollama ollama-stock || true)"
if [ -z "$STOCK_BIN" ]; then
  "$AQ_SCRIPTS_DIR/install-ollama-stock.sh"
  STOCK_BIN="$(aq_require_ollama ollama-stock)"
fi
export PATH="$(dirname "$STOCK_BIN"):$PATH"
export OLLAMA_HOST="http://127.0.0.1:$PORT"

echo "OLLAMA_HOST = $OLLAMA_HOST"
echo "Pulling $BASE_MODEL ..."
"$STOCK_BIN" pull "$BASE_MODEL"

echo "Creating aquila_heretic from Modelfile.Heretic ..."
"$STOCK_BIN" create aquila_heretic -f "$MODELFILE"

echo ""
echo "Smoke test (API)..."
curl -fsS --max-time 180 "http://127.0.0.1:$PORT/api/generate" \
  -H "Content-Type: application/json" \
  -d '{"model":"aquila_heretic","prompt":"Reply with exactly: ok","stream":false}' \
  | { "$(aq_python)" -c "import sys,json; print('Response:', json.load(sys.stdin).get('response',''))" 2>/dev/null || cat; }

echo ""
echo "Done. Set .env:"
echo "  OLLAMA_BASE_URL=http://127.0.0.1:$PORT"
echo "  OLLAMA_MODEL=aquila_heretic"
