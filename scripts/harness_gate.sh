#!/usr/bin/env bash
# Aquila harness gate — required code scenarios must pass before shipping code-mode changes.
# Usage:
#   ./scripts/harness_gate.sh
#   ./scripts/harness_gate.sh --engine stock --runs 3
#   ./scripts/harness_gate.sh --allow-degraded
#   ./scripts/harness_gate.sh --baseline

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PY="$(aq_python)"
export AQUILA_DATA_ROOT="${AQUILA_DATA_ROOT:-$AQ_REPO_ROOT}"
export PYTHONPATH="$AQ_REPO_ROOT/agent${PYTHONPATH:+:$PYTHONPATH}"

cd "$AQ_REPO_ROOT"
exec "$PY" -m agent.core.harness_gate "$@"
