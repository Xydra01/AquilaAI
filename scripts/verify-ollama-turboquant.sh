#!/usr/bin/env bash
# Quick check that Ollama is reachable and list installed models.
# TurboQuant is active only when serve was started via ollama-serve-turboquant.*.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BASE="$(aq_normalize_url "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}")"
echo "Ollama base: $BASE"

if ! aq_probe "$BASE"; then
  echo "ERROR: Ollama not reachable. Start: ./scripts/ollama-serve-turboquant.sh" >&2
  exit 1
fi

names="$(curl -fsS --max-time 5 "$BASE/api/tags" \
  | "$(aq_python)" -c "import sys,json; print('\n'.join(m.get('name','') for m in json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "")"

echo "Models:"
echo "$names" | sed 's/^/  - /'
for want in aquila aquila-tq-32k aquila-tq-64k aquila-tq-96k; do
  if echo "$names" | grep -q "$want"; then
    echo "  [ok] $want"
  else
    echo "  [--] $want (not installed - ollama create ...)"
  fi
done

echo ""
echo "TurboQuant env (current shell - serve may use different vars):"
echo "  OLLAMA_KV_CACHE_TYPE   = ${OLLAMA_KV_CACHE_TYPE:-<unset>}"
echo "  OLLAMA_NEW_ENGINE      = ${OLLAMA_NEW_ENGINE:-<unset>}"
echo "  OLLAMA_FLASH_ATTENTION = ${OLLAMA_FLASH_ATTENTION:-<unset>}"
echo ""
echo "If TQ is unsupported, upgrade Ollama or build from ollama/ollama PR #15505."
