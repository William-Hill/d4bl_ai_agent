-- supabase/migrations/20260331000002_scraped_content_compatibility_view.sql
--
-- Step 1: Rename the original table to legacy (preserving data for rollback)
-- Step 2: Create a view with the same name for backward compatibility
-- Step 3: Add INSTEAD OF INSERT trigger so vector_store.py writes still work
--
-- IMPORTANT: Run migrate_documents.py BEFORE applying this migration.
-- Rollback: DROP TRIGGER IF EXISTS scraped_content_vectors_insert ON scraped_content_vectors;
--           DROP FUNCTION IF EXISTS scraped_content_vectors_insert_fn();
--           DROP VIEW scraped_content_vectors;
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

-- INSTEAD OF INSERT trigger: translates inserts on the view into the new tables
-- so that vector_store.py (which does INSERT INTO scraped_content_vectors) keeps working.
CREATE OR REPLACE FUNCTION scraped_content_vectors_insert_fn()
RETURNS TRIGGER AS $$
DECLARE
    new_doc_id UUID;
BEGIN
    INSERT INTO documents (source_url, content_type, job_id, metadata, created_at, updated_at)
    VALUES (NEW.url, COALESCE(NEW.content_type, 'html'), NEW.job_id,
            COALESCE(NEW.metadata, '{}'), now(), now())
    ON CONFLICT (source_url) WHERE source_url IS NOT NULL
    DO UPDATE SET updated_at = now()
    RETURNING id INTO new_doc_id;

    INSERT INTO document_chunks (document_id, content, chunk_index, embedding, token_count, created_at)
    VALUES (new_doc_id, NEW.content, 0, NEW.embedding, NULL, now())
    ON CONFLICT (document_id, chunk_index) DO UPDATE
    SET content = EXCLUDED.content, embedding = EXCLUDED.embedding;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER scraped_content_vectors_insert
    INSTEAD OF INSERT ON scraped_content_vectors
    FOR EACH ROW
    EXECUTE FUNCTION scraped_content_vectors_insert_fn();
