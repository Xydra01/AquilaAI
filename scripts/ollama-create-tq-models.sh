#!/usr/bin/env bash
# Create all Aquila TurboQuant models against the server on OLLAMA_HOST (default 11435).
# Usage (repo root):
#   ./scripts/ollama-serve-turboquant-port.sh   # separate terminal, must be running first
#   ./scripts/ollama-create-tq-models.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

OLLAMA_BIN_RESOLVED="$(aq_require_ollama ollama-turboquant)"
BIN_DIR="$(dirname "$OLLAMA_BIN_RESOLVED")"
if command -v cygpath >/dev/null 2>&1; then
  BIN_DIR="$(cygpath -u "$BIN_DIR")"
fi
export PATH="$BIN_DIR:$PATH"

HOST_URL="$(aq_normalize_url "${OLLAMA_HOST:-http://127.0.0.1:11435}")"
export OLLAMA_HOST="$HOST_URL"
echo "OLLAMA_HOST = $HOST_URL"
echo ""

if ! aq_probe "$HOST_URL"; then
  echo "TurboQuant Ollama is not reachable at $HOST_URL" >&2
  echo "" >&2
  echo "Start the server in another terminal, then re-run this script:" >&2
  echo "  ./scripts/ollama-serve-turboquant-port.sh" >&2
  exit 1
fi

names=("aquila-tq-32k" "aquila-tq-64k" "aquila-tq-96k")
files=("Modelfile.tq-32k" "Modelfile.tq-64k" "Modelfile.tq-96k")

cd "$AQ_REPO_ROOT"
for i in "${!names[@]}"; do
  name="${names[$i]}"
  file="${files[$i]}"
  if [ ! -f "$AQ_REPO_ROOT/$file" ]; then
    echo "Skip $name - missing $file"
    continue
  fi
  echo "Creating $name from $file ..."
  "$OLLAMA_BIN_RESOLVED" create "$name" -f "$AQ_REPO_ROOT/$file"
  echo "  [ok] $name"
done

echo ""
echo "Done. Suggested .env:"
echo "  OLLAMA_BASE_URL=$HOST_URL"
echo "  OLLAMA_MODEL=aquila-tq-32k   # light tasks"
echo "  OLLAMA_MODEL=aquila-tq-64k   # default extended"
echo "  OLLAMA_MODEL=aquila-tq-96k   # max context"
