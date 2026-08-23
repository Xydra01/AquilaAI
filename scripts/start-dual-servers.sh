#!/usr/bin/env bash
# start-dual-servers.sh - Starts both stock and TurboQuant Ollama servers in the background

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting Stock Ollama Server (Port 11434)..."
nohup "$DIR/ollama-serve-stock.sh" > "$DIR/../Agent-Logs/ollama-stock.log" 2>&1 &
STOCK_PID=$!

echo "Starting TurboQuant Ollama Server (Port 11435)..."
nohup "$DIR/ollama-serve-turboquant-port.sh" > "$DIR/../Agent-Logs/ollama-turboquant.log" 2>&1 &
TQ_PID=$!

echo "Both servers are now running in the background!"
echo "Stock PID: $STOCK_PID"
echo "TurboQuant PID: $TQ_PID"
echo "Logs are being written to Agent-Logs/"
