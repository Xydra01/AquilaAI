#!/usr/bin/env bash
# Launch the Aquila Remote Companion server (FastAPI + PWA).
# Cross-platform: Git Bash (Windows), macOS, Linux.
#
# Usage:
#   ./scripts/aquila-remote-serve.sh                 # bind 0.0.0.0:8800
#   ./scripts/aquila-remote-serve.sh --host 100.x.y.z --port 8800
#   AQUILA_REMOTE_HOST=100.x.y.z ./scripts/aquila-remote-serve.sh
#
# Binding to your Tailscale interface address (100.x.y.z) means only devices on
# your private VPN can reach it. 0.0.0.0 also works because Tailscale + the OS
# firewall gate inbound traffic, but a specific Tailscale IP is tighter.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

HOST="${AQUILA_REMOTE_HOST:-0.0.0.0}"
PORT="${AQUILA_REMOTE_PORT:-8800}"
RELOAD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --reload) RELOAD="--reload"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

PY="$(aq_python)"

echo "Aquila Remote Companion"
echo "  Host: $HOST   Port: $PORT"

export PYTHONPATH="$AQ_REPO_ROOT"

# Show the Host ID + a fresh pairing code so you can pair a new device.
( cd "$AQ_REPO_ROOT/agent" && "$PY" -m remote.host_cli pair-code ) || true
echo ""
echo "Open http://$HOST:$PORT (or your Tailscale IP) on a paired device."
echo ""

# Run from agent/ so 'remote.server' and the bare-module brain imports resolve.
cd "$AQ_REPO_ROOT/agent"
exec "$PY" -m uvicorn remote.server:app --host "$HOST" --port "$PORT" $RELOAD
