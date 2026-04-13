#!/bin/bash
# start.sh - Unified Cross-Platform Startup

# Determine the correct activation path
if [ -d "ai-agent-env/Scripts" ]; then
    # Windows
    source ai-agent-env/Scripts/activate
else
    # macOS / Linux
    source ai-agent-env/bin/activate
fi

# Run the agent
python agent/main.py
