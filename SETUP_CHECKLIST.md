# Setup Checklist

Use this checklist to ensure everything is configured correctly before running the application.

## ✅ Prerequisites

- [ ] Python 3.14+ installed
- [ ] `uv` package manager installed
- [ ] Redis installed (`brew install redis`)
- [ ] Supabase account created
- [ ] OpenAI API account with credits
- [ ] Whapi.cloud account configured

## ✅ Environment Setup

- [ ] Copied `.env.example` to `.env`
- [ ] Set `SUPABASE_URL` in `.env`
- [ ] Set `SUPABASE_KEY` (service_role key) in `.env`
- [ ] Set `WHAPI_TOKEN` in `.env`
- [ ] Set `WHAPI_API_URL` in `.env` (default: `https://gate.whapi.cloud`)
- [ ] Set `OPENAI_API_KEY` in `.env`
- [ ] Set `REDIS_URL` in `.env` (default: `redis://localhost:6379`)
- [ ] Set `MEDIA_BUCKET_NAME` in `.env` (default: `whatsapp-media`)

## ✅ Supabase Configuration

### Database Migrations

Run SQL migrations in order from the `migrations/` directory:

- [ ] `001_initial_schema_updates.sql` - Creates messages table with core fields
- [ ] `001_create_processing_jobs_table.sql` - Creates retry job tracking table
- [ ] `002_add_processing_jobs_indexes.sql` - Adds performance indexes
- [ ] `004_message_timestamp.sql` - Updates timestamp handling to `message_sent_at`

### Required Tables

Your Supabase database needs these 3 tables:

#### 1. messages table
```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID,  -- References users table
  content TEXT,
  origin TEXT NOT NULL,  -- 'agent' or 'user'
  type TEXT NOT NULL,    -- 'text', 'voice', 'image', 'video', 'document', 'audio'
  message_sent_at TIMESTAMPTZ,  -- When message was actually sent
  chat_id TEXT NOT NULL,
  media_url TEXT,  -- URL to stored media in Supabase Storage
  whapi_message_id TEXT UNIQUE,
  extracted_media_content TEXT,  -- PDF extracted text
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 2. message_processing_jobs table
```sql
CREATE TABLE message_processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'completed', 'failed'
  retry_count INTEGER DEFAULT 0,
  max_retries INTEGER DEFAULT 3,
  webhook_payload JSONB,  -- Original webhook data for retry
  last_attempt_at TIMESTAMPTZ,
  next_retry_at TIMESTAMPTZ,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 3. users table (required, not created by migrations)
```sql
-- You must create this table yourself
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT UNIQUE NOT NULL,  -- Phone number for lookup
  -- Add other user fields as needed
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Storage Bucket

- [ ] Created storage bucket named `whatsapp-media`
- [ ] Set bucket to Public (or configured appropriate RLS policies)

## ✅ Local Testing Setup

- [ ] Installed ngrok (`brew install ngrok`)
- [ ] Can run ngrok: `ngrok http 8000`

## ✅ Whapi Configuration

- [ ] Configured webhook URL in Whapi dashboard
- [ ] Set webhook to `https://your-ngrok-url.ngrok.io/webhook`
- [ ] Set authentication header: `Bearer <your_whapi_token>`

## ✅ Running the Application

Start these in 3 separate terminal windows:

### Terminal 1: Redis
```bash
redis-server
```
- [ ] Redis is running
- [ ] Can connect with `redis-cli ping` (returns PONG)

### Terminal 2: FastAPI
```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- [ ] Server started successfully
- [ ] Can access http://localhost:8000/health
- [ ] Returns: `{"status": "healthy"}`

### Terminal 3: RQ Worker
```bash
./run_worker.sh
# or
uv run rq worker whatsapp-messages --url redis://localhost:6379
```
- [ ] Worker connected to Redis
- [ ] Worker is listening for jobs

### Terminal 4 (Optional): Ngrok
```bash
ngrok http 8000
```
- [ ] Ngrok running
- [ ] HTTPS URL available
- [ ] Updated Whapi webhook URL with ngrok URL

## ✅ Testing

- [ ] Send real WhatsApp message to business number
- [ ] Message appears in FastAPI logs
- [ ] Job appears in RQ worker logs
- [ ] Message inserted into Supabase `messages` table

## ✅ Voice Message Testing (Optional)

- [ ] Send voice message to WhatsApp business number
- [ ] Voice file downloaded from Whapi
- [ ] Voice file uploaded to Supabase Storage bucket
- [ ] Transcription completed via Whisper API
- [ ] Message with transcription saved to database

## ✅ PDF Document Testing (Optional)

- [ ] Send PDF document to WhatsApp business number
- [ ] PDF downloaded from Whapi
- [ ] PDF uploaded to Supabase Storage bucket
- [ ] PDF text extracted using OpenAI Vision API
- [ ] Message with extracted content saved in `extracted_media_content` field

## ✅ Monitoring

- [ ] Check RQ queue status: `uv run rq info --url redis://localhost:6379`
- [ ] Monitor Supabase dashboard for new messages
- [ ] Check `message_processing_jobs` table for any failed jobs

## ✅ Retry Worker (Optional)

For automatic retry of failed processing jobs:

```bash
# Run once manually
uv run python -m workers.retry_pending

# Or schedule with cron (every 30 minutes)
*/30 * * * * cd /path/to/message_memory && uv run python -m workers.retry_pending
```

- [ ] Retry worker can run successfully
- [ ] Failed jobs are retried and marked as completed

## 🎉 Success Criteria

Your setup is complete when:

1. ✅ You can receive a text message webhook
2. ✅ Message is processed and appears in Supabase
3. ✅ Voice messages are transcribed correctly
4. ✅ PDF documents have text extracted and stored
5. ✅ Failed jobs are tracked in `message_processing_jobs` table
6. ✅ No errors in logs

## 🐛 Common Issues

### "Connection refused" errors
→ Make sure Redis is running

### "Invalid API key" errors
→ Check your API keys in `.env`

### "Table does not exist" errors
→ Run all SQL migrations in the `migrations/` directory in order
→ Make sure you created the `users` table

### Webhook not receiving
→ Check ngrok is running and Whapi webhook URL is correct

### Voice transcription fails
→ Verify OpenAI API key and account has credits

### PDF extraction fails
→ Verify OpenAI API key, check worker logs for errors

### Media processing fails
→ Check `message_processing_jobs` table for error details, run retry worker

### "User not found" warnings
→ Make sure the `users` table exists and has phone numbers populated

---

**Need help?** Check [README.md](README.md) for detailed instructions or [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment.
