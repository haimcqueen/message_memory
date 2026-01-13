"""FastAPI application for WhatsApp webhook receiver."""
import logging
import json
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks, Request, Body
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.models import WhapiWebhook, N8nErrorWebhook
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

# Add CORS middleware
# Development origins + production Vercel domains
cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://my.publyc.app",
    "https://publyc-app.vercel.app"
]

# Add production origins if in production
if settings.environment == "production":
    cors_origins.extend([
        "https://my.publyc.app",
        "https://publyc-app.vercel.app",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app" if settings.environment == "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
transcription_queue = Queue("transcription", connection=redis_conn)


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
    error_data: N8nErrorWebhook = Body(...),
    authorization: str = Header(None)
):
    """
    Receive n8n workflow error notifications and send alert to admin.

    Args:
        error_data: Error information from n8n (accepts any format)
        authorization: Bearer token for authentication
    """
    from app.models import N8nErrorWebhook

    # Verify n8n token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    if token != settings.n8n_webhook_api_key:
        raise HTTPException(status_code=403, detail="Invalid n8n API key")

    logger.info("Received n8n error notification")
    payload_dict = error_data.model_dump()
    logger.error(f"n8n error payload: {payload_dict}")

    # Extract data from n8n payload
    mode = payload_dict.get("mode")
    workflow_url = payload_dict.get("workflow")
    error_message = payload_dict.get("error") or payload_dict.get("error_message")
    last_node = payload_dict.get("lastNodeExecuted")
    stack_trace = payload_dict.get("stack")

    # Skip manual test executions
    if mode == "manual":
        logger.info("Skipping notification for manual execution")
        return JSONResponse(
            status_code=200,
            content={"status": "skipped", "message": "Manual execution ignored"}
        )

    # Send notification to hardcoded admin phone number
    admin_chat_id = "4915202618514@s.whatsapp.net"

    try:
        from utils.whapi_messaging import send_whatsapp_message

        # Build notification message
        notification_parts = ["🚨 n8n Workflow Error"]

        if workflow_url:
            notification_parts.append(f"\n📋 Workflow: {workflow_url}")

        if error_message:
            notification_parts.append(f"\n❌ Error: {error_message}")
        else:
            notification_parts.append(f"\n❌ Error: Unknown error")

        if last_node:
            notification_parts.append(f"\n🔧 Failed Node: {last_node}")

        if mode:
            notification_parts.append(f"\n🔄 Mode: {mode}")

        notification_text = "".join(notification_parts)

        send_whatsapp_message(admin_chat_id, notification_text)
        logger.info(f"Sent n8n error notification to admin: {admin_chat_id}")
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to send notification"}
        )

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Error notification sent"}
    )


@app.post("/webhook/transcribe")
async def transcribe_webhook(
    request: Request,
    authorization: str = Header(None)
):
    """
    Receive transcription request and queue for processing.

    Accepts two types of requests:
    - Dual recording: {"userId": "...", "recordingType": "dual", "micUrl": "...", "systemUrl": "..."}
    - IRL recording: {"userId": "...", "recordingType": "irl", "irlUrl": "..."}

    Auth: Bearer token (N8N_WEBHOOK_API_KEY)
    """
    from app.models_transcription import DualRecordingRequest, IrlRecordingRequest

    # Verify Bearer token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    if token != settings.n8n_webhook_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Parse request body
    body = await request.json()
    recording_type = body.get("recordingType")

    # Validate based on recording type
    if recording_type == "dual":
        validated_request = DualRecordingRequest(**body)
    elif recording_type == "irl":
        validated_request = IrlRecordingRequest(**body)
    else:
        raise HTTPException(status_code=400, detail="Invalid recordingType. Must be 'dual' or 'irl'")

    logger.info(f"Received {recording_type} transcription request for user {validated_request.userId}")

    # Import here to avoid circular dependency
    from workers.transcription_elevenlabs import process_transcription

    # Enqueue job
    job = transcription_queue.enqueue(
        process_transcription,
        validated_request.model_dump(),
        job_timeout="30m"  # Transcription can take time for long recordings
    )

    logger.info(f"Job {job.id} queued for transcription (user: {validated_request.userId})")

    return JSONResponse(
        status_code=200,
        content={"status": "queued", "job_id": job.id, "userId": validated_request.userId}
    )

    return JSONResponse(
        status_code=200,
        content={"status": "queued", "job_id": job.id, "userId": validated_request.userId}
    )


class MemorySearchRequest(BaseModel):
    user_id: str
    query: str
    limit: int = 5


@app.post("/api/v1/memory/search")
async def search_memory_endpoint(
    request: MemorySearchRequest,
    authorization: str = Header(None)
):
    """
    Search for relevant facts/memories for a user.
    """
    # Verify auth (using n8n key for simplicity for now, or add a new one)
    if not authorization or not authorization.startswith("Bearer "):
         raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    # Allow either Whapi or N8n token for now
    if token != settings.n8n_webhook_api_key and token != settings.whapi_token:
         raise HTTPException(status_code=403, detail="Invalid API key")

    # Import helper functions
    from workers.database import search_memories
    from utils.llm import generate_embedding

    try:
        # 1. Generate embedding for the query
        query_vector = generate_embedding(request.query)
        if not query_vector:
             return JSONResponse(status_code=500, content={"error": "Failed to generate embedding"})

        # 2. Search DB
        results = search_memories(request.user_id, query_vector, limit=request.limit)

        return JSONResponse(
            status_code=200,
            content={"status": "success", "results": results}
        )
    except Exception as e:
        logger.error(f"Search API error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


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
            "transcribe": "/webhook/transcribe",
            "debug": "/webhook/debug",
            "search": "/api/v1/memory/search"
        }
    }
