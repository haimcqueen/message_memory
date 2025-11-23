# WhatsApp Message Memory

A production-ready FastAPI system that logs all WhatsApp messages from a business account to Supabase, with automatic voice transcription, PDF extraction, and automatic retry logic.

## Features

- Receives Whapi WhatsApp webhooks
- Processes text, voice, image, video, document, and audio messages
- **Transcribes voice messages** using OpenAI Whisper API
- **Extracts text from PDFs** using OpenAI Vision API (gpt-4o-mini)
- Stores messages in Supabase database
- Uploads media files to Supabase Storage
- **Background job processing** with RQ (Redis Queue)
- **Automatic retry logic** with exponential backoff
- **Failed job tracking** with retry worker for resilient message processing
- **Railway deployment ready** with Procfile and configuration

## Tech Stack

- **FastAPI** - Webhook receiver
- **RQ + Redis** - Job queue for background processing
- **Supabase** - Database + Storage
- **OpenAI Whisper** - Voice transcription
- **OpenAI GPT-4o-mini** - PDF extraction
- **Tenacity** - Retry logic with exponential backoff
- **Railway** - Deployment platform (optional)

## Project Structure

```
message_memory/
├── app/
│   ├── main.py              # FastAPI app + webhook endpoint
│   └── models.py            # Pydantic models for webhooks
├── workers/
│   ├── jobs.py              # RQ job handlers
│   ├── transcription.py     # Whisper API integration
│   ├── media.py             # Media handling & PDF extraction
│   ├── database.py          # Supabase operations
│   └── retry_pending.py     # Retry worker for failed jobs
├── utils/
│   ├── config.py            # Environment configuration
│   └── supabase_client.py   # Supabase client singleton
├── migrations/              # Database schema migrations
│   ├── 001_initial_schema_updates.sql
│   ├── 001_create_processing_jobs_table.sql
│   ├── 002_add_processing_jobs_indexes.sql
│   └── 004_message_timestamp.sql
├── .env.example             # Template for environment setup
├── Procfile                 # Process definitions for Railway
├── railway.json             # Railway deployment config
├── run_worker.sh            # Shell script to start RQ worker
└── README.md
```

## Prerequisites

- Python 3.14+
- Redis server
- Supabase account and project
- OpenAI API key
- Whapi.cloud account

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### 2. Set Up Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here
WHAPI_TOKEN=your_whapi_bearer_token_here
WHAPI_API_URL=https://gate.whapi.cloud
OPENAI_API_KEY=sk-your_openai_api_key_here
REDIS_URL=redis://localhost:6379
MEDIA_BUCKET_NAME=whatsapp-media
ENVIRONMENT=development
```

### 3. Set Up Supabase

#### Run Database Migrations

Execute the SQL files in the `migrations/` directory in order using the Supabase SQL Editor:

1. `001_initial_schema_updates.sql` - Create messages table and initial indexes
2. `001_create_processing_jobs_table.sql` - Create retry job tracking table
3. `002_add_processing_jobs_indexes.sql` - Add indexes for efficient retry queries
4. `004_message_timestamp.sql` - Update timestamp handling

**Note:** You must also have a `users` table with at least `id` and `phone` columns for user lookup functionality.

#### Create Storage Bucket

1. Go to Supabase Dashboard → Storage
2. Create a new bucket named `whatsapp-media`
3. Set it to **Public** (or configure RLS policies as needed)

### 4. Install and Start Redis

```bash
# macOS
brew install redis
brew services start redis

# Or manually start Redis
redis-server
```

## Running the Application

You'll need **3 terminal windows**:

### Terminal 1: Start Redis

```bash
redis-server
```

### Terminal 2: Start FastAPI Server

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at [http://localhost:8000](http://localhost:8000)

### Terminal 3: Start RQ Worker

```bash
./run_worker.sh
# or
uv run rq worker whatsapp-messages --url redis://localhost:6379
```

### Optional: Start Retry Worker

For automatic retry of failed message processing:

```bash
# Run once
uv run python -m workers.retry_pending

# Or schedule with cron every 30 minutes
*/30 * * * * cd /path/to/message_memory && uv run python -m workers.retry_pending
```

## Testing Locally with Webhooks

Since Whapi needs a public HTTPS URL, use **ngrok** to expose your local server:

### 1. Install ngrok

```bash
brew install ngrok
```

### 2. Expose Local Server

```bash
ngrok http 8000
```

This will give you a public URL like: `https://abc123.ngrok.io`

### 3. Configure Whapi Webhook

1. Go to Whapi.cloud dashboard
2. Navigate to your channel settings
3. Set webhook URL to: `https://abc123.ngrok.io/webhook`
4. Set authentication header: `Bearer <your_whapi_token>`

### 4. Test

Send a message to your WhatsApp business number and watch the logs!

## API Endpoints

### `GET /health`
Health check endpoint

### `GET /`
API information

### `POST /webhook`
Whapi webhook receiver (requires Bearer token authentication)

## How It Works

1. **Webhook Receipt**: FastAPI receives Whapi webhook
2. **Authentication**: Validates Bearer token
3. **Job Queuing**: Enqueues message to RQ for background processing
4. **Processing**:
   - Extracts message data (type, content, sender)
   - Determines origin (agent vs user)
   - For voice messages:
     - Downloads file from Whapi
     - Uploads to Supabase Storage
     - Transcribes with Whisper API
   - For PDFs:
     - Downloads file from Whapi
     - Uploads to Supabase Storage
     - Extracts text using OpenAI Vision API (gpt-4o-mini)
     - Stores extracted content in `extracted_media_content` field
   - For other media (images, videos, audio):
     - Downloads from Whapi
     - Uploads to Supabase Storage
5. **Storage**: Inserts message into Supabase
6. **Error Handling**: Failed jobs stored in `message_processing_jobs` table
7. **Retry Logic**: Retry worker processes failed jobs with exponential backoff

## Retry Logic

All external API calls have automatic retry with exponential backoff:

- **Whisper API**: 5 attempts (2s → 32s backoff)
- **Supabase Operations**: 3 attempts (1s → 8s backoff)
- **Media Download/Upload**: 3 attempts (1s → 8s backoff)
- **PDF Extraction**: 3 attempts (2s → 16s backoff)

Failed jobs after all retries are stored in the `message_processing_jobs` table and can be retried using the retry worker.

## Monitoring

### Check RQ Queue Status

```bash
uv run rq info --url redis://localhost:6379
```

### View Failed Jobs in Supabase

```sql
SELECT * FROM message_processing_jobs WHERE status = 'failed' ORDER BY created_at DESC;
```

### Check Retry Worker Results

```bash
uv run python -m workers.retry_pending
```

## Deployment

This project is ready to deploy to Railway with included configuration files:

- `Procfile` - Defines web and worker processes
- `railway.json` - Railway build and deployment settings
- `.railwayignore` - Files to exclude from deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed Railway deployment instructions.

Estimated production cost: **~$15/month** on Railway (includes web service, worker, and Redis).

## Troubleshooting

### Redis connection errors

Make sure Redis is running:
```bash
redis-cli ping
# Should return: PONG
```

### Supabase authentication errors

- Verify `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
- Use the **service_role** key (not anon key)

### Webhook not receiving messages

- Check ngrok is running and URL is correct in Whapi
- Verify Whapi Bearer token matches your `.env`
- Check FastAPI logs for authentication errors

### Voice transcription failing

- Verify OpenAI API key is valid
- Check you have credits in OpenAI account
- Voice files must be in supported format (Whapi provides OGG)

### PDF extraction failing

- Verify OpenAI API key is valid
- Check you have credits in OpenAI account
- PDF processing uses gpt-4o-mini (cost-effective model)
- Check worker logs for OpenAI API errors

### Media processing failures

- Check `message_processing_jobs` table for error details
- Run retry worker to attempt reprocessing
- Verify Supabase storage bucket is created and accessible
- Check Whapi API credentials and rate limits

## License

MIT
test