#!/usr/bin/env bash
# Pull Qwopus Coder GGUF + create aquila_qwopus on stock Ollama (default port 11434).
# Requires: ./scripts/ollama-serve-stock.sh running in another terminal.
# Usage: ./scripts/ollama-create-qwopus.sh [--port N]

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PORT="11434"
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

MODELFILE="$AQ_REPO_ROOT/modelfiles/Modelfile.Qwopus"
if [ ! -f "$MODELFILE" ]; then
  MODELFILE="$AQ_REPO_ROOT/Modelfile.Qwopus"
fi
BASE_MODEL="hf.co/Jackrong/Qwopus3.5-9B-Coder-GGUF:Q4_K_M"

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

echo "Creating aquila_qwopus from Modelfile.Qwopus ..."
"$STOCK_BIN" create aquila_qwopus -f "$MODELFILE"

echo ""
echo "Smoke test — chat with thinking..."
curl -fsS --max-time 180 "http://127.0.0.1:$PORT/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"model":"aquila_qwopus","messages":[{"role":"user","content":"Reply with exactly: ok"}],"stream":false,"think":true}' \
  | "$(aq_python)" -c "
import sys, json
d = json.load(sys.stdin)
msg = d.get('message') or {}
content = (msg.get('content') or '').strip()
thinking = (msg.get('thinking') or '').strip()
print('content:', content[:120] or '(empty)')
print('thinking_chars:', len(thinking))
"

echo ""
echo "Smoke test — strict JSON schema..."
curl -fsS --max-time 180 "http://127.0.0.1:$PORT/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"model":"aquila_qwopus","messages":[{"role":"user","content":"Output JSON only: {\"reasoning\":\"ok\",\"tools\":[]}"}],"stream":false,"think":false,"format":"json"}' \
  | "$(aq_python)" -c "
import sys, json
d = json.load(sys.stdin)
content = (d.get('message') or {}).get('content') or ''
print('json_preview:', content[:160])
"

echo ""
echo "Done. Set .env:"
echo "  OLLAMA_BASE_URL=http://127.0.0.1:$PORT"
echo "  OLLAMA_MODEL=aquila_qwopus"
