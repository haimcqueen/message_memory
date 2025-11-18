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


@app.post("/webhook/n8n-error")
async def n8n_error_webhook(
    error_data: "N8nErrorWebhook",
    authorization: str = Header(None)
):
    """
    Receive n8n workflow error notifications and notify user with retry.

    Args:
        error_data: Error information from n8n
        authorization: Bearer token for authentication
    """
    from app.models import N8nErrorWebhook

    # Verify n8n token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    if token != settings.n8n_webhook_api_key:
        raise HTTPException(status_code=403, detail="Invalid n8n API key")

    logger.info(f"Received n8n error for user_id: {error_data.user_id}")
    logger.error(f"n8n error message: {error_data.error_message}")

    # Get chat_id if not provided
    chat_id = error_data.chat_id
    if not chat_id:
        from workers.database import get_chat_id_by_user_id
        try:
            chat_id = get_chat_id_by_user_id(error_data.user_id)
            if not chat_id:
                logger.error(f"No chat_id found for user_id: {error_data.user_id}")
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "No chat_id found for user"}
                )
        except Exception as e:
            logger.error(f"Error looking up chat_id: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Failed to lookup chat_id"}
            )

    # Send notification to user
    try:
        from utils.whapi_messaging import send_whatsapp_message
        send_whatsapp_message(
            chat_id,
            "We encountered an issue processing your message and are retrying now. You'll hear from us shortly."
        )
        logger.info(f"Sent error notification to chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
        # Continue even if notification fails

    # Trigger retry by re-sending to n8n
    try:
        from workers.batching import add_message_to_batch
        # Trigger n8n batching for this user (will send immediately with count=1)
        add_message_to_batch(
            chat_id=chat_id,
            content="[n8n error retry]",
            user_id=error_data.user_id,
            session_id=None
        )
        logger.info(f"Triggered n8n retry for user_id: {error_data.user_id}")
    except Exception as e:
        logger.error(f"Failed to trigger n8n retry: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to trigger retry"}
        )

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Error handled, retry triggered"}
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
            "n8n_error": "/webhook/n8n-error",
            "debug": "/webhook/debug"
        }
    }
