-- Add bias_motivation column and clean up fbi_crime_stats schema.
-- bias_motivation stores hate crime bias labels (e.g. "Anti-Black or African American")
-- while race stores actual race values for arrest data (e.g. "White", "Black").

-- 1. Add bias_motivation column
ALTER TABLE fbi_crime_stats ADD COLUMN IF NOT EXISTS bias_motivation VARCHAR(100);

-- 2. Allow race to be NULL (hate crime rows won't have it)
ALTER TABLE fbi_crime_stats ALTER COLUMN race DROP NOT NULL;

-- 3. Widen race column to VARCHAR(100) for consistency
ALTER TABLE fbi_crime_stats ALTER COLUMN race TYPE VARCHAR(100);

-- 4. Migrate existing hate crime data: move bias labels from race to bias_motivation
UPDATE fbi_crime_stats
SET bias_motivation = race, race = NULL
WHERE category IN ('hate_crime', 'hate_crime_category');

-- 5. Replace unique constraint with functional index that handles NULLs
DROP INDEX IF EXISTS uq_fbi_crime_key;
CREATE UNIQUE INDEX uq_fbi_crime_key ON fbi_crime_stats(
    state_abbrev, offense, COALESCE(race, ''), COALESCE(bias_motivation, ''), year, category
);
