web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: rq worker whatsapp-messages --url $REDIS_URL
scheduler: rqscheduler --url $REDIS_URL --interval 10
