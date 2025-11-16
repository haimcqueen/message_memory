-- Migration: Replace timestamp column with message_sent_at
-- This properly tracks when messages were actually sent (from WhatsApp)
-- versus created_at which tracks when we inserted the record

-- Step 1: Add the new message_sent_at column
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS message_sent_at TIMESTAMPTZ;

-- Step 2: Drop the old timestamp column (int8) since it's not being used correctly
ALTER TABLE messages
DROP COLUMN IF EXISTS timestamp;

-- Step 3: Update indexes
DROP INDEX IF EXISTS idx_messages_chat_id_timestamp;

-- Index for session detection (filter by chat_id, order by message_sent_at)
CREATE INDEX IF NOT EXISTS idx_messages_chat_id_message_sent_at ON messages(chat_id, message_sent_at DESC);

-- Index for API queries (filter by user_id, order by message_sent_at)
CREATE INDEX IF NOT EXISTS idx_messages_user_id_message_sent_at ON messages(user_id, message_sent_at DESC);

-- Index for querying all messages in a specific session
CREATE INDEX IF NOT EXISTS idx_messages_session_time ON messages(session_id, message_sent_at DESC);

-- Step 4: Add unique index on whapi_message_id for deduplication
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_whapi_message_id ON messages(whapi_message_id);
