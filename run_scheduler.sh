#!/bin/bash
# RQ Scheduler for processing delayed n8n batch jobs

echo "Starting RQ Scheduler for n8n batching..."
echo "Press Ctrl+C to stop"
echo ""

rqscheduler --host ${REDIS_HOST:-localhost} --port ${REDIS_PORT:-6379} --db ${REDIS_DB:-0} --interval 10
