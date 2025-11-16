-- Migration: Move retry logic from messages table to message_processing_jobs table
-- This separates message data from processing/retry logic

-- Step 1: Create the new message_processing_jobs table
CREATE TABLE IF NOT EXISTS message_processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  retry_count INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 3,
  webhook_payload JSONB,
  last_attempt_at TIMESTAMPTZ,
  next_retry_at TIMESTAMPTZ,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON message_processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_next_retry ON message_processing_jobs(next_retry_at) WHERE status = 'failed';
CREATE INDEX IF NOT EXISTS idx_processing_jobs_message_id ON message_processing_jobs(message_id);

-- Step 2: Migrate existing failed messages to the new table
-- This preserves the retry state of currently failing messages
INSERT INTO message_processing_jobs (
  message_id,
  status,
  retry_count,
  max_retries,
  webhook_payload,
  last_attempt_at,
  next_retry_at,
  created_at
)
SELECT
  id,
  'failed',
  COALESCE(retry_count, 0),
  3, -- default max_retries
  webhook_payload,
  last_retry_at,
  last_retry_at, -- use last_retry_at as next_retry_at initially
  created_at
FROM messages
WHERE processing_status = 'failed'
ON CONFLICT DO NOTHING;

-- Step 3: Drop the retry-related columns from messages table
-- (We'll do this in a separate migration after verifying the new system works)
-- ALTER TABLE messages DROP COLUMN IF EXISTS processing_status;
-- ALTER TABLE messages DROP COLUMN IF EXISTS retry_count;
-- ALTER TABLE messages DROP COLUMN IF EXISTS last_retry_at;
-- ALTER TABLE messages DROP COLUMN IF EXISTS webhook_payload;

-- For now, we'll just comment these out and run them manually after testing
COMMENT ON TABLE message_processing_jobs IS 'Tracks processing state and retries for messages that require async processing (media download, transcription, etc.)';
