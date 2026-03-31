-- supabase/migrations/20260331000001_add_document_tables.sql

-- Ensure pgvector extension exists
CREATE EXTENSION IF NOT EXISTS vector;

-- Parent table: one row per source document
CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT,
    source_url          TEXT,
    storage_path        TEXT,
    content_type        VARCHAR(50) NOT NULL,
    source_key          VARCHAR(100),
    job_id              UUID REFERENCES research_jobs(job_id),
    extraction_metadata JSONB DEFAULT '{}',
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_content_type ON documents(content_type);
CREATE INDEX IF NOT EXISTS idx_documents_source_key ON documents(source_key);
CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(job_id) WHERE job_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_source_url ON documents(source_url) WHERE source_url IS NOT NULL;

-- Child table: N chunks per document
CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    token_count     INTEGER,
    embedding       vector(1024),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_doc_position ON document_chunks(document_id, chunk_index);
