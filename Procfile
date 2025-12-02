web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: uv run rq worker whatsapp-messages transcription --url $REDIS_URL --with-scheduler
