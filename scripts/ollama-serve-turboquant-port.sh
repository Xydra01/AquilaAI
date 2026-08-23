#!/usr/bin/env bash
# TurboQuant Ollama on port 11435 (stock default is ollama-serve-stock.sh on 11434).
# Aquila: OLLAMA_BASE_URL=http://127.0.0.1:11435  OLLAMA_MODEL=aquila-tq-64k
# See docs/ollama-dual-setup.md

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/ollama-serve-turboquant.sh" --port 11435 "$@"
