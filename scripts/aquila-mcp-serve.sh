#!/usr/bin/env bash
# Start Aquila MCP host (stdio) for Cursor / MCP clients.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$AQ_REPO_ROOT/agent"
export AQUILA_DATA_ROOT="${AQUILA_DATA_ROOT:-$AQ_REPO_ROOT}"
PY="$(aq_python)"
exec "$PY" mcp_host.py "$@"
