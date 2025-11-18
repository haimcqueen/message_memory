-- Add link_preview to message_type enum
ALTER TYPE message_type ADD VALUE IF NOT EXISTS 'link_preview';
