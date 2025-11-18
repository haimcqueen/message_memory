#!/bin/bash

# Script to run the retry worker
# This is meant to be called by cron every 30 minutes

# Works in both local and production (Railway) environments
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use uv run for production (Railway) or fall back to direct python for local
if command -v uv &> /dev/null; then
    uv run python workers/retry_pending.py
else
    # Local development fallback
    PYTHONPATH=. python workers/retry_pending.py
fi
