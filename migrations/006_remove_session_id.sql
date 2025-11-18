-- Remove session_id column from messages table
-- Session tracking is not currently used and causes sorting issues with NULL values

-- Drop the index that uses session_id
DROP INDEX IF EXISTS idx_messages_session_time;

-- Drop the session_id column
ALTER TABLE messages DROP COLUMN IF EXISTS session_id;
