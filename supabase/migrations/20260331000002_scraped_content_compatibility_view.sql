-- supabase/migrations/20260331000002_scraped_content_compatibility_view.sql
--
-- Step 1: Rename the original table to legacy (preserving data for rollback)
-- Step 2: Create a view with the same name for backward compatibility
--
-- IMPORTANT: Run migrate_documents.py BEFORE applying this migration.
-- Rollback: DROP VIEW scraped_content_vectors;
--           ALTER TABLE scraped_content_vectors_legacy RENAME TO scraped_content_vectors;

ALTER TABLE IF EXISTS scraped_content_vectors
    RENAME TO scraped_content_vectors_legacy;

CREATE OR REPLACE VIEW scraped_content_vectors AS
SELECT
    dc.id,
    d.job_id,
    d.source_url AS url,
    dc.content,
    d.content_type,
    d.metadata,
    dc.embedding,
    d.created_at,
    d.updated_at
FROM document_chunks dc
JOIN documents d ON dc.document_id = d.id;
