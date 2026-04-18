-- Add new upload_status enum values used by the document indexing pipeline.
-- ``indexed`` marks a document upload whose chunks have been written to the
-- vector store. ``processing_failed`` marks an approval where chunking or
-- embedding raised; the admin can retry via the admin API.

ALTER TYPE upload_status ADD VALUE IF NOT EXISTS 'indexed';
ALTER TYPE upload_status ADD VALUE IF NOT EXISTS 'processing_failed';
