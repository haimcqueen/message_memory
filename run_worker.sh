#!/bin/bash
# Start RQ worker for processing WhatsApp messages

echo "Starting RQ worker with built-in scheduler for WhatsApp messages..."
echo "Press Ctrl+C to stop"
echo ""

# Unset any environment variables that might override .env file
unset OPENAI_API_KEY

OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run rq worker whatsapp-messages --url redis://localhost:6379 --with-scheduler
