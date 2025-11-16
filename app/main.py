"""FastAPI application for WhatsApp webhook receiver."""
import logging
import json
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.models import WhapiWebhook
from utils.config import settings
from redis import Redis
from rq import Queue

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="WhatsApp Message Logger", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging."""
    body = await request.body()
    logger.error(f"Validation error for {request.url.path}")
    logger.error(f"Request body: {body.decode()}")
    logger.error(f"Validation errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# Initialize Redis and RQ
redis_conn = Redis.from_url(settings.redis_url)
message_queue = Queue("whatsapp-messages", connection=redis_conn)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "whatsapp-message-logger"}


@app.post("/webhook/whapi")
async def whapi_webhook(
    webhook: WhapiWebhook,
    authorization: str = Header(None)
):
    """
    Receive Whapi webhook and queue for processing.

    Args:
        webhook: Whapi webhook payload
        authorization: Bearer token for authentication
    """
    # Verify Whapi token
    # TODO: Re-enable auth after testing
    # if not authorization or not authorization.startswith("Bearer "):
    #     raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    #
    # token = authorization.replace("Bearer ", "")
    # if token != settings.whapi_token:
    #     raise HTTPException(status_code=403, detail="Invalid Whapi token")

    logger.info(f"Received authorization header: {authorization}")

    # Ignore status updates and other non-message webhooks
    if not webhook.messages:
        logger.info(f"Ignoring non-message webhook: {webhook.event.type}")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "not a message webhook"}
        )

    logger.info(f"Received webhook with {len(webhook.messages)} message(s)")

    # Process each message in the webhook
    for message in webhook.messages:
        logger.info(
            f"Queueing message {message.id} of type {message.type} "
            f"from {message.from_name or 'API'} (chat_id: {message.chat_id})"
        )

        # Import here to avoid circular dependency
        from workers.jobs import process_whatsapp_message

        # Enqueue job
        job = message_queue.enqueue(
            process_whatsapp_message,
            message.model_dump(by_alias=True),
            job_timeout="10m"
        )

        logger.info(f"Job {job.id} queued for message {message.id}")

    # Return 200 immediately
    return JSONResponse(
        status_code=200,
        content={"status": "queued", "message_count": len(webhook.messages)}
    )


@app.post("/webhook/debug")
async def debug_webhook(request: Request):
    """Debug endpoint to see raw webhook payloads."""
    body = await request.body()
    data = json.loads(body.decode())
    logger.info("=" * 80)
    logger.info("DEBUG WEBHOOK RECEIVED")
    logger.info(f"Full payload: {json.dumps(data, indent=2)}")
    logger.info("=" * 80)
    return JSONResponse(
        status_code=200,
        content={"status": "logged", "message": "Check server logs for full payload"}
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "WhatsApp Message Logger",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "webhook": "/webhook/whapi",
            "debug": "/webhook/debug"
        }
    }
