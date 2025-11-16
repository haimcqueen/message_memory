-- Add missing columns to messages table
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS chat_id TEXT,
ADD COLUMN IF NOT EXISTS media_url TEXT,
ADD COLUMN IF NOT EXISTS whapi_message_id TEXT;

-- Add index for chat_id (for session detection queries)
CREATE INDEX IF NOT EXISTS idx_messages_chat_id_timestamp ON messages(chat_id, timestamp DESC);

-- Create failed_jobs table
CREATE TABLE IF NOT EXISTS failed_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  webhook_payload JSONB NOT NULL,
  error_message TEXT NOT NULL,
  retry_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_attempt TIMESTAMPTZ DEFAULT NOW()
);

-- Optional: Add index on users.phone for faster lookups
-- (Only run this if you don't already have an index on the phone column)
-- CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
