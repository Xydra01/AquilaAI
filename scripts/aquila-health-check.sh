#!/usr/bin/env bash
# Aquila pytest health check - tiered test runs before release or heavy changes.
# Usage:
#   ./scripts/aquila-health-check.sh quick
#   ./scripts/aquila-health-check.sh smoke
#   ./scripts/aquila-health-check.sh full
#   ./scripts/aquila-health-check.sh heretic
#   ./scripts/aquila-health-check.sh qwopus
#   ./scripts/aquila-health-check.sh full --eject

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TIER="${1:-quick}"
EJECT="no"
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --eject) EJECT="yes"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

PY="$(aq_python)"
echo "Using python: $PY"

run_pytest() {
  ( cd "$AQ_REPO_ROOT/agent" && "$PY" -m pytest "$@" )
}

eject_models() {
  local base model
  base="$(aq_normalize_url "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}")"
  model="${OLLAMA_MODEL:-aquila}"
  echo "Ejecting loaded models on $base (model hint: $model)..."
  curl -fsS --max-time 30 "$base/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"keep_alive\":0}" >/dev/null 2>&1 \
    && echo "  keep_alive=0 sent." \
    || echo "  Warning: eject request failed"
}

echo ""
echo "=== Aquila health check: $TIER ==="
echo ""

case "$TIER" in
  quick)
    run_pytest tests/ -m "not live" -q --tb=short
    ;;
  smoke)
    run_pytest tests/ -m "not live" -q --tb=short
    run_pytest tests/test_live_ollama.py tests/test_live_context_smoke.py -m live -v --tb=short
    ;;
  full)
    run_pytest tests/ -v --tb=short
    ;;
  heretic)
    export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
    export OLLAMA_MODEL="${OLLAMA_MODEL:-aquila_heretic}"
    echo "OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
    echo "OLLAMA_MODEL=$OLLAMA_MODEL"
    run_pytest tests/ -m heretic -v --tb=short
    ;;
  qwopus)
    export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
    export OLLAMA_MODEL="${OLLAMA_MODEL:-aquila_qwopus}"
    echo "OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
    echo "OLLAMA_MODEL=$OLLAMA_MODEL"
    run_pytest tests/ -m qwopus -v --tb=short
    ;;
  *)
    echo "Unknown tier: $TIER (use quick | smoke | full | heretic | qwopus)" >&2
    exit 1
    ;;
esac

if [ "$EJECT" = "yes" ] && { [ "$TIER" = "smoke" ] || [ "$TIER" = "full" ] || [ "$TIER" = "heretic" ] || [ "$TIER" = "qwopus" ]; }; then
  eject_models
fi

echo ""
echo "=== $TIER health check passed ==="
