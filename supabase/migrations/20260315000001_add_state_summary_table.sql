CREATE TABLE IF NOT EXISTS state_summary (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    state_name VARCHAR(100) NOT NULL,
    metric VARCHAR(200) NOT NULL,
    race VARCHAR(50) NOT NULL DEFAULT 'total',
    year INTEGER NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    sample_size INTEGER,
    CONSTRAINT uq_state_summary_source_state_metric_race_year
        UNIQUE (source, state_fips, metric, race, year)
);
CREATE INDEX IF NOT EXISTS idx_state_summary_source ON state_summary (source);
CREATE INDEX IF NOT EXISTS idx_state_summary_state_fips ON state_summary (state_fips);
CREATE INDEX IF NOT EXISTS idx_state_summary_source_metric ON state_summary (source, metric);
