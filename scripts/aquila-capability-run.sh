#!/usr/bin/env bash
# Aquila capability harness — replay JSONL, pytest, or live matrix runs.
# Usage:
#   ./scripts/aquila-capability-run.sh pytest
#   ./scripts/aquila-capability-run.sh replay <jsonl_path>
#   ./scripts/aquila-capability-run.sh clear-lock
#   ./scripts/aquila-capability-run.sh matrix [--engine stock|tq|both] [--scenario ID]

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

MODE="${1:-pytest}"
shift || true
PY="$(aq_python)"
export AQUILA_DATA_ROOT="${AQUILA_DATA_ROOT:-$AQ_REPO_ROOT}"
export PYTHONPATH="$AQ_REPO_ROOT/agent${PYTHONPATH:+:$PYTHONPATH}"
BASELINES="$AQ_REPO_ROOT/Agent-Logs/capability-baselines"
mkdir -p "$BASELINES"
MAX_WALL="${AQUILA_HARNESS_MAX_WALL_S:-600}"

cd "$AQ_REPO_ROOT/agent"

_run_matrix() {
  local engine="both"
  local scenario=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --engine) engine="${2:-both}"; shift 2 ;;
      --scenario) scenario="${2:-}"; shift 2 ;;
      *) shift ;;
    esac
  done
  local -a cmd=( "$PY" capability_harness.py run_matrix --engine "$engine" )
  if [ -n "$scenario" ]; then
    cmd+=( --scenario "$scenario" )
  fi
  echo "Harness matrix (engine=$engine, max_wall=${MAX_WALL}s) ..."
  if command -v timeout >/dev/null 2>&1; then
    timeout "${MAX_WALL}" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

case "$MODE" in
  clear-lock)
    "$PY" capability_harness.py clear_lock
    ;;
  matrix)
    _run_matrix "$@"
    ;;
  replay)
    JSONL_PATH="${1:-}"
    if [ -z "$JSONL_PATH" ]; then
      echo "Provide JSONL path: ./scripts/aquila-capability-run.sh replay Agent-Logs/foo.jsonl" >&2
      exit 1
    fi
    case "$JSONL_PATH" in
      /*|[A-Za-z]:*) ABS="$JSONL_PATH" ;;
      *) ABS="$AQ_REPO_ROOT/$JSONL_PATH" ;;
    esac
    AQ_JSONL="$ABS" AQ_BASELINES="$BASELINES" "$PY" - <<'PYEOF'
import json, os, sys
from pathlib import Path
from capability_scorecard import score_jsonl_for_scenario, write_scorecard_jsonl

path = Path(os.environ["AQ_JSONL"])
card = score_jsonl_for_scenario(path, "persona_build_lore")
out = Path(os.environ["AQ_BASELINES"]) / "scorecard.jsonl"
write_scorecard_jsonl(card, out)
print(json.dumps(card.to_dict(), indent=2))
sys.exit(0 if card.passed else 1)
PYEOF
    ;;
  replay-all|pytest)
    "$PY" -m pytest \
      tests/test_capability_scorecard.py \
      tests/test_capability_replay.py \
      tests/test_capability_harness.py \
      tests/test_mcp_harness.py \
      -q --tb=short
    ;;
  *)
    echo "Unknown mode: $MODE (use pytest | replay | matrix | clear-lock)" >&2
    exit 1
    ;;
esac

echo ""
echo "=== Capability run: $MODE OK ==="
