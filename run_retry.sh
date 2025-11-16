#!/bin/bash

# Script to run the retry worker
# This is meant to be called by cron every 30 minutes

cd /Users/haibui/00_Projects/message_memory
PYTHONPATH=. /Users/haibui/00_Projects/message_memory/.venv/bin/python workers/retry_pending.py
