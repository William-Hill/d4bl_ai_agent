-- CDC + ACS race-weighted health outcome estimates
CREATE TABLE IF NOT EXISTS cdc_acs_race_estimates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips_code VARCHAR(11) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    geography_name VARCHAR(200) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    year INTEGER NOT NULL,
    measure VARCHAR(50) NOT NULL,
    race VARCHAR(20) NOT NULL,
    health_rate FLOAT NOT NULL,
    race_population_share FLOAT NOT NULL,
    estimated_value FLOAT NOT NULL,
    total_population INTEGER,
    confidence_low FLOAT,
    confidence_high FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cdc_acs_race_key
    ON cdc_acs_race_estimates(fips_code, year, measure, race);
CREATE INDEX IF NOT EXISTS ix_cdc_acs_race_state
    ON cdc_acs_race_estimates(state_fips, measure, year, race);
CREATE INDEX IF NOT EXISTS ix_cdc_acs_race_geo_type
    ON cdc_acs_race_estimates(geography_type, year);

ALTER TABLE cdc_acs_race_estimates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read cdc_acs_race_estimates"
    ON cdc_acs_race_estimates FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Admins can manage cdc_acs_race_estimates"
    ON cdc_acs_race_estimates FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'))
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
