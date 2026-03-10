-- CDC Health Outcomes (CDC PLACES)
CREATE TABLE IF NOT EXISTS cdc_health_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips_code VARCHAR(11) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    geography_name TEXT NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    year INTEGER NOT NULL,
    measure VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    data_value FLOAT NOT NULL,
    data_value_type VARCHAR(50) NOT NULL,
    low_confidence_limit FLOAT,
    high_confidence_limit FLOAT,
    total_population INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cdc_health_outcome_key
    ON cdc_health_outcomes(fips_code, year, measure, data_value_type);
CREATE INDEX IF NOT EXISTS ix_cdc_health_state_measure
    ON cdc_health_outcomes(state_fips, measure, year);

-- EPA Environmental Justice (EJScreen)
CREATE TABLE IF NOT EXISTS epa_environmental_justice (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tract_fips VARCHAR(11) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    state_name VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    indicator VARCHAR(200) NOT NULL,
    raw_value FLOAT,
    percentile_state FLOAT,
    percentile_national FLOAT,
    demographic_index FLOAT,
    population INTEGER,
    minority_pct FLOAT,
    low_income_pct FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_epa_ej_key
    ON epa_environmental_justice(tract_fips, year, indicator);
CREATE INDEX IF NOT EXISTS ix_epa_ej_state_indicator
    ON epa_environmental_justice(state_fips, indicator, year);

-- FBI Crime Stats
CREATE TABLE IF NOT EXISTS fbi_crime_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_abbrev VARCHAR(2) NOT NULL,
    state_name VARCHAR(50) NOT NULL,
    offense VARCHAR(200) NOT NULL,
    category VARCHAR(100) NOT NULL,
    race VARCHAR(50) NOT NULL,
    ethnicity VARCHAR(50),
    year INTEGER NOT NULL,
    value FLOAT NOT NULL,
    population INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fbi_crime_key
    ON fbi_crime_stats(state_abbrev, offense, race, year, category);
CREATE INDEX IF NOT EXISTS ix_fbi_crime_state_race_year
    ON fbi_crime_stats(state_abbrev, race, year);

-- BLS Labor Statistics
CREATE TABLE IF NOT EXISTS bls_labor_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id VARCHAR(50) NOT NULL,
    state_fips VARCHAR(2),
    state_name VARCHAR(50),
    metric VARCHAR(200) NOT NULL,
    race VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    period VARCHAR(10) NOT NULL,
    value FLOAT NOT NULL,
    footnotes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bls_labor_key
    ON bls_labor_statistics(series_id, year, period);
CREATE INDEX IF NOT EXISTS ix_bls_labor_metric_race_year
    ON bls_labor_statistics(metric, race, year);

-- HUD Fair Housing
CREATE TABLE IF NOT EXISTS hud_fair_housing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips_code VARCHAR(11) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    geography_name TEXT NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    year INTEGER NOT NULL,
    indicator VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    value FLOAT NOT NULL,
    race_group_a VARCHAR(50),
    race_group_b VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hud_fair_housing_key
    ON hud_fair_housing(fips_code, year, indicator, race_group_a, race_group_b);
CREATE INDEX IF NOT EXISTS ix_hud_fh_state_indicator
    ON hud_fair_housing(state_fips, indicator, year);

-- USDA Food Access
CREATE TABLE IF NOT EXISTS usda_food_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tract_fips VARCHAR(11) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    county_fips VARCHAR(5),
    state_name VARCHAR(50),
    county_name VARCHAR(100),
    year INTEGER NOT NULL,
    indicator VARCHAR(200) NOT NULL,
    value FLOAT NOT NULL,
    urban_rural VARCHAR(10),
    population INTEGER,
    poverty_rate FLOAT,
    median_income FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_usda_food_access_key
    ON usda_food_access(tract_fips, year, indicator);
CREATE INDEX IF NOT EXISTS ix_usda_fa_state_indicator
    ON usda_food_access(state_fips, indicator, year);

-- DOE Civil Rights (CRDC)
CREATE TABLE IF NOT EXISTS doe_civil_rights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    district_id VARCHAR(20) NOT NULL,
    district_name TEXT NOT NULL,
    state VARCHAR(2) NOT NULL,
    state_name VARCHAR(50) NOT NULL,
    school_year VARCHAR(9) NOT NULL,
    metric VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    race VARCHAR(50) NOT NULL,
    value FLOAT NOT NULL,
    total_enrollment INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_doe_civil_rights_key
    ON doe_civil_rights(district_id, school_year, metric, race);
CREATE INDEX IF NOT EXISTS ix_doe_cr_state_metric_race
    ON doe_civil_rights(state, metric, race);

-- Police Violence Incidents
CREATE TABLE IF NOT EXISTS police_violence_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id VARCHAR(100) NOT NULL UNIQUE,
    date DATE NOT NULL,
    year INTEGER NOT NULL,
    state VARCHAR(2) NOT NULL,
    city VARCHAR(200),
    county VARCHAR(200),
    race VARCHAR(50),
    age INTEGER,
    gender VARCHAR(20),
    armed_status VARCHAR(100),
    cause_of_death VARCHAR(200),
    circumstances TEXT,
    criminal_charges VARCHAR(200),
    agency VARCHAR(200),
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pv_state_race_year
    ON police_violence_incidents(state, race, year);

-- Enable RLS on all new tables (read-only for authenticated users)
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'cdc_health_outcomes',
            'epa_environmental_justice',
            'fbi_crime_stats',
            'bls_labor_statistics',
            'hud_fair_housing',
            'usda_food_access',
            'doe_civil_rights',
            'police_violence_incidents'
        ])
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);

        EXECUTE format(
            'CREATE POLICY "Authenticated users can read %1$s" ON %1$I FOR SELECT USING (auth.role() = ''authenticated'')',
            tbl
        );

        EXECUTE format(
            'CREATE POLICY "Admins can manage %1$s" ON %1$I FOR ALL USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = ''admin'')) WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = ''admin''))',
            tbl
        );
    END LOOP;
END $$;
