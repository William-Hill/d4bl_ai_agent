-- Data Sources table
CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    default_schedule VARCHAR(100),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_data_sources_source_type ON data_sources(source_type);
CREATE INDEX IF NOT EXISTS ix_data_sources_enabled ON data_sources(enabled);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_data_sources_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER data_sources_updated_at
    BEFORE UPDATE ON data_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_data_sources_updated_at();

-- RLS: admins only
ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can manage data sources"
    ON data_sources
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role = 'admin'
        )
    );

-- Ingestion Runs table
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    dagster_run_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    triggered_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    trigger_type VARCHAR(50) NOT NULL DEFAULT 'manual',
    records_ingested INTEGER,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_detail TEXT
);

CREATE INDEX IF NOT EXISTS ix_ingestion_runs_data_source_id ON ingestion_runs(data_source_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_runs_status ON ingestion_runs(status);
CREATE INDEX IF NOT EXISTS ix_ingestion_runs_started_at ON ingestion_runs(started_at);

ALTER TABLE ingestion_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can manage ingestion runs"
    ON ingestion_runs
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role = 'admin'
        )
    );

-- Data Lineage table
CREATE TABLE IF NOT EXISTS data_lineage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
    target_table VARCHAR(255) NOT NULL,
    record_id UUID NOT NULL,
    source_url TEXT,
    source_hash VARCHAR(128),
    transformation JSONB,
    quality_score FLOAT,
    coverage_metadata JSONB,
    bias_flags JSONB,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_data_lineage_ingestion_run_id ON data_lineage(ingestion_run_id);
CREATE INDEX IF NOT EXISTS ix_data_lineage_target_table ON data_lineage(target_table);
CREATE INDEX IF NOT EXISTS ix_data_lineage_record_id ON data_lineage(record_id);

ALTER TABLE data_lineage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can manage data lineage"
    ON data_lineage
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role = 'admin'
        )
    );

-- Keyword Monitors table
CREATE TABLE IF NOT EXISTS keyword_monitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    keywords JSONB NOT NULL DEFAULT '[]',
    source_ids JSONB NOT NULL DEFAULT '[]',
    schedule VARCHAR(100),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_keyword_monitors_enabled ON keyword_monitors(enabled);

ALTER TABLE keyword_monitors ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can manage keyword monitors"
    ON keyword_monitors
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.role = 'admin'
        )
    );
