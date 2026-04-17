-- Upload status tracking
CREATE TYPE upload_type AS ENUM ('datasource', 'document', 'query', 'feature_request');
CREATE TYPE upload_status AS ENUM ('pending_review', 'approved', 'rejected', 'processing', 'live');
CREATE TYPE feature_request_status AS ENUM ('open', 'acknowledged', 'planned', 'closed');

CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    upload_type upload_type NOT NULL,
    status upload_status NOT NULL DEFAULT 'pending_review',
    file_path TEXT,
    original_filename TEXT,
    file_size_bytes INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}',
    reviewer_id UUID,
    reviewer_notes TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_uploads_user_id ON uploads(user_id);
CREATE INDEX idx_uploads_status ON uploads(status);
CREATE INDEX idx_uploads_type ON uploads(upload_type);
CREATE INDEX idx_uploads_created_at ON uploads(created_at DESC);

CREATE TABLE uploaded_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    data JSONB NOT NULL,
    UNIQUE(upload_id, row_index)
);

CREATE INDEX idx_uploaded_datasets_upload_id ON uploaded_datasets(upload_id);

CREATE TABLE example_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    summary_format TEXT NOT NULL DEFAULT 'detailed',
    description TEXT NOT NULL,
    curated_answer TEXT,
    relevant_sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_example_queries_upload_id ON example_queries(upload_id);

CREATE TABLE feature_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    upload_id UUID REFERENCES uploads(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    who_benefits TEXT NOT NULL,
    example TEXT,
    status feature_request_status NOT NULL DEFAULT 'open',
    admin_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feature_requests_user_id ON feature_requests(user_id);
CREATE INDEX idx_feature_requests_status ON feature_requests(status);
