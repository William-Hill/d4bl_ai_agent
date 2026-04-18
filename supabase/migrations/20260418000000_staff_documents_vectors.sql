-- Relax scraped_content_vectors.job_id so staff-contributed documents
-- (which do not belong to a research job) can live in the same table.
-- Add a `source` column to distinguish research-job content from staff uploads.

ALTER TABLE scraped_content_vectors
    ALTER COLUMN job_id DROP NOT NULL;

ALTER TABLE scraped_content_vectors
    ADD COLUMN IF NOT EXISTS source VARCHAR(30) NOT NULL DEFAULT 'research_job';

CREATE INDEX IF NOT EXISTS scraped_content_vectors_source_idx
    ON scraped_content_vectors(source);

-- Enforce the invariant that every research-job row still has a job_id.
-- Staff-upload rows are allowed to have job_id = NULL; other future source
-- types are unconstrained by this check.
ALTER TABLE scraped_content_vectors
    ADD CONSTRAINT scraped_content_vectors_source_job_id_check
    CHECK (source <> 'research_job' OR job_id IS NOT NULL);

-- Staff-upload rows will have source = 'staff_upload' and job_id = NULL.
-- Research-job rows keep source = 'research_job' and job_id = <uuid>.
