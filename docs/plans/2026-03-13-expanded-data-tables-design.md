# Expanded Data Tables — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create 7 new database tables for additional racial equity data sources, following existing schema patterns.

**Architecture:** Single Supabase migration file + SQLAlchemy models. All tables use normalized/long format with a `race` column and single `value`/count column for consistency with existing tables.

**Tech Stack:** PostgreSQL (Supabase), SQLAlchemy ORM, Supabase RLS policies

---

## Tables

### 1. census_demographics
Decennial race/ethnicity population counts by county/tract.
- **Source**: Census Bureau API (#90)
- **Unique key**: `(geo_id, year, race)`
- **Query index**: `(state_fips, year)`

### 2. cdc_mortality
Mortality data by race, cause of death, and county.
- **Source**: CDC WONDER (#91)
- **Unique key**: `(county_fips, year, cause_of_death, race, age_group)`
- **Query index**: `(state_fips, cause_of_death, year)`

### 3. bjs_incarceration
Prison/jail population by race, state level.
- **Source**: DOJ Bureau of Justice Statistics (#92)
- **Unique key**: `(state_abbrev, year, facility_type, metric, race, gender)`
- **Query index**: `(state_abbrev, race, year)`

### 4. congress_votes
Congressional voting records on equity-related legislation.
- **Source**: ProPublica Congress API (#93)
- **Unique key**: `(bill_id, congress, chamber)`
- **Query index**: `(congress, subject)`

### 5. vera_incarceration
County-level incarceration data by race (normalized from wide CSV).
- **Source**: Vera Institute GitHub CSV (#94)
- **Unique key**: `(fips, year, facility_type, race)`
- **Query index**: `(state, race, year)`

### 6. traffic_stops
Traffic stop data by race and department (normalized from wide CSV).
- **Source**: Stanford Open Policing Project (#95)
- **Unique key**: `(state, department, year, race)`
- **Query index**: `(state, race, year)`

### 7. eviction_data
Eviction filing rates by county/tract.
- **Source**: Eviction Lab / Princeton (#96)
- **Unique key**: `(geo_id, year)`
- **Query index**: `(state_fips, year)`

## Deliverables

1. `supabase/migrations/20260313000001_add_expanded_data_tables.sql` — DDL + indexes + RLS
2. 7 new SQLAlchemy model classes in `src/d4bl/infra/database.py`
3. Run migration against staging Supabase DB

## Patterns

- All tables: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `created_at TIMESTAMPTZ DEFAULT now()`
- Unique constraints for idempotent `ON CONFLICT ... DO UPDATE` upserts
- RLS: authenticated=read, admin=all (matching existing tables)
- Normalized format: one row per (geography, year, race, metric) tuple
