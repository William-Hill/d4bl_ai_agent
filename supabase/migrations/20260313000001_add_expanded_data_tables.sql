-- Census Decennial Demographics (race/ethnicity population)
CREATE TABLE IF NOT EXISTS census_demographics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geo_id VARCHAR(11) NOT NULL,
    geo_type VARCHAR(10) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    state_name VARCHAR(50),
    county_name VARCHAR(200),
    year INTEGER NOT NULL,
    race VARCHAR(50) NOT NULL,
    population INTEGER,
    pct_of_total FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_census_demographics_key
    ON census_demographics(geo_id, year, race);
CREATE INDEX IF NOT EXISTS ix_census_demo_state_year
    ON census_demographics(state_fips, year);

-- CDC WONDER Mortality (state + national, via SODA API)
CREATE TABLE IF NOT EXISTS cdc_mortality (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geo_id VARCHAR(20) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    state_fips VARCHAR(2),
    state_name VARCHAR(100),
    year INTEGER NOT NULL,
    cause_of_death VARCHAR(200) NOT NULL,
    race VARCHAR(100) NOT NULL DEFAULT 'total',
    deaths INTEGER,
    age_adjusted_rate REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cdc_mortality_key
    ON cdc_mortality(geo_id, year, cause_of_death, race);
CREATE INDEX IF NOT EXISTS ix_cdc_mortality_state_year
    ON cdc_mortality(state_fips, year, cause_of_death, race);
CREATE INDEX IF NOT EXISTS ix_cdc_mortality_geo_type
    ON cdc_mortality(geography_type, year);

-- DOJ Bureau of Justice Statistics Incarceration
CREATE TABLE IF NOT EXISTS bjs_incarceration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_abbrev VARCHAR(2) NOT NULL,
    state_name VARCHAR(50),
    year INTEGER NOT NULL,
    facility_type VARCHAR(20) NOT NULL,
    metric VARCHAR(100) NOT NULL,
    race VARCHAR(50) NOT NULL,
    gender VARCHAR(20) NOT NULL,
    value FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bjs_incarceration_key
    ON bjs_incarceration(state_abbrev, year, facility_type, metric, race, gender);
CREATE INDEX IF NOT EXISTS ix_bjs_inc_state_race_year
    ON bjs_incarceration(state_abbrev, race, year);

-- ProPublica Congress Votes
CREATE TABLE IF NOT EXISTS congress_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bill_id VARCHAR(50) NOT NULL,
    bill_number VARCHAR(20),
    title TEXT,
    subject VARCHAR(200),
    congress INTEGER NOT NULL,
    chamber VARCHAR(10) NOT NULL,
    vote_date DATE,
    result VARCHAR(50),
    yes_votes INTEGER,
    no_votes INTEGER,
    topic_tags JSON,
    url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_congress_votes_key
    ON congress_votes(bill_id, congress, chamber);
CREATE INDEX IF NOT EXISTS ix_congress_votes_congress_subject
    ON congress_votes(congress, subject);

-- Vera Institute Incarceration Trends (county-level, normalized)
CREATE TABLE IF NOT EXISTS vera_incarceration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips VARCHAR(5) NOT NULL,
    state VARCHAR(2) NOT NULL,
    county_name VARCHAR(200),
    year INTEGER NOT NULL,
    urbanicity VARCHAR(20),
    facility_type VARCHAR(20) NOT NULL,
    race VARCHAR(50) NOT NULL,
    population INTEGER,
    total_pop INTEGER,
    rate_per_100k FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_vera_incarceration_key
    ON vera_incarceration(fips, year, facility_type, race);
CREATE INDEX IF NOT EXISTS ix_vera_inc_state_race_year
    ON vera_incarceration(state, race, year);

-- Stanford Open Policing Traffic Stops (normalized)
CREATE TABLE IF NOT EXISTS traffic_stops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state VARCHAR(2) NOT NULL,
    county_name VARCHAR(200),
    department VARCHAR(200),
    year INTEGER NOT NULL,
    race VARCHAR(50) NOT NULL,
    total_stops INTEGER,
    search_conducted INTEGER,
    contraband_found INTEGER,
    arrest_made INTEGER,
    citation_issued INTEGER,
    search_rate FLOAT,
    hit_rate FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_traffic_stops_key
    ON traffic_stops(state, department, year, race);
CREATE INDEX IF NOT EXISTS ix_traffic_stops_state_race_year
    ON traffic_stops(state, race, year);

-- Eviction Lab Data
CREATE TABLE IF NOT EXISTS eviction_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geo_id VARCHAR(11) NOT NULL,
    geo_type VARCHAR(10) NOT NULL,
    state_fips VARCHAR(2),
    geo_name VARCHAR(200),
    year INTEGER NOT NULL,
    population INTEGER,
    poverty_rate FLOAT,
    pct_renter_occupied FLOAT,
    median_gross_rent FLOAT,
    eviction_filings INTEGER,
    evictions INTEGER,
    eviction_rate FLOAT,
    eviction_filing_rate FLOAT,
    pct_nonwhite FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_eviction_data_key
    ON eviction_data(geo_id, year);
CREATE INDEX IF NOT EXISTS ix_eviction_data_state_year
    ON eviction_data(state_fips, year);

-- Enable RLS on all new tables
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'census_demographics',
            'cdc_mortality',
            'bjs_incarceration',
            'congress_votes',
            'vera_incarceration',
            'traffic_stops',
            'eviction_data'
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
