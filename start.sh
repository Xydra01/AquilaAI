#!/bin/bash
# start.sh - Unified Cross-Platform Startup
cd "$(dirname "$0")" || exit 1

# Determine the correct activation path
if [ -d "ai-agent-env/Scripts" ]; then
    # Windows
    source ai-agent-env/Scripts/activate
else
    # macOS / Linux
    source ai-agent-env/bin/activate
fi
#start the docker container
docker compose up -d
# Run the agent through qt
python agent/gui.py
