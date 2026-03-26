"""
Database models and connection for storing research queries and results
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from d4bl.settings import get_settings

Base = declarative_base()


def _utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ResearchJob(Base):
    """Model for storing research job queries and results"""
    __tablename__ = "research_jobs"

    job_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=True, index=True)
    query = Column(Text, nullable=False, index=True)
    summary_format = Column(String(20), nullable=False, default="detailed")
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)  # Store the full result dict as JSON
    research_data = Column(JSON, nullable=True)  # Store research data for use as reference in evaluations
    error = Column(Text, nullable=True)
    logs = Column(JSON, nullable=True)  # Store logs array as JSON
    created_at = Column(DateTime, nullable=False, default=_utc_now, index=True)
    updated_at = Column(DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)
    completed_at = Column(DateTime, nullable=True)
    # No ForeignKey -- auth.users is managed by Supabase, not SQLAlchemy
    user_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "job_id": str(self.job_id),
            "trace_id": self.trace_id,
            "query": self.query,
            "summary_format": self.summary_format,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "research_data": self.research_data,
            "error": self.error,
            "logs": self.logs,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "user_id": str(self.user_id) if self.user_id else None,
        }


class EvaluationResult(Base):
    """Store evaluator outputs for spans"""
    __tablename__ = "evaluation_results"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    span_id = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    job_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)  # Link to ResearchJob
    eval_name = Column(String(100), nullable=False, index=True)
    label = Column(String(100), nullable=True)
    score = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)
    input_text = Column(Text, nullable=True)
    output_text = Column(Text, nullable=True)
    context_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now, index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "job_id": str(self.job_id) if self.job_id else None,
            "eval_name": self.eval_name,
            "label": self.label,
            "score": self.score,
            "explanation": self.explanation,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "context_text": self.context_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ModelEvalRun(Base):
    """Track evaluation runs per model version for regression detection."""
    __tablename__ = "model_eval_runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(50), nullable=False)
    base_model_name = Column(String(100), nullable=False)
    task = Column(String(50), nullable=False, index=True)
    test_set_hash = Column(String(64), nullable=False)
    metrics = Column(JSONB, nullable=False)
    ship_decision = Column(String(20), nullable=False)
    blocking_failures = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now, index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "base_model_name": self.base_model_name,
            "task": self.task,
            "test_set_hash": self.test_set_hash,
            "metrics": self.metrics,
            "ship_decision": self.ship_decision,
            "blocking_failures": self.blocking_failures,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CensusIndicator(Base):
    """Race-disaggregated Census ACS indicators by geography."""
    __tablename__ = "census_indicators"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(11), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)   # state | county | tract
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    race = Column(String(50), nullable=False)
    metric = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    margin_of_error = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        # Composite index to support common query filters
        Index(
            "ix_census_indicator_state_geo_metric_race_year",
            "state_fips",
            "geography_type",
            "metric",
            "race",
            "year",
        ),
        # Ensure idempotent upserts on core identity
        UniqueConstraint(
            "fips_code",
            "year",
            "race",
            "metric",
            name="uq_census_indicator_key",
        ),
        {"comment": "Census ACS 5-year estimates, race-disaggregated"},
    )


class PolicyBill(Base):
    """State legislation tracked via OpenStates."""
    __tablename__ = "policy_bills"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    bill_id = Column(String(50), nullable=False)
    bill_number = Column(String(20), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    topic_tags = Column(JSON, nullable=True)
    session = Column(String(20), nullable=False, index=True)
    introduced_date = Column(Date, nullable=True)
    last_action_date = Column(Date, nullable=True)
    url = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    updated_at = Column(DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        # Support common filters for policy tracker views
        Index(
            "ix_policy_bill_state_status_session",
            "state",
            "status",
            "session",
        ),
        # Idempotent upserts per state/session/bill id
        UniqueConstraint(
            "state",
            "bill_id",
            "session",
            name="uq_policy_bill_key",
        ),
    )


class DataSource(Base):
    """Admin-configured data source for ingestion."""

    __tablename__ = "data_sources"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    source_type = Column(
        String(50),
        nullable=False,
        comment="api|file_upload|web_scrape|rss_feed|database|mcp",
    )
    config = Column(JSON, nullable=False, default=dict)
    default_schedule = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_data_sources_source_type", "source_type"),
        Index("ix_data_sources_enabled", "enabled"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "source_type": self.source_type,
            "config": self.config,
            "default_schedule": self.default_schedule,
            "enabled": self.enabled,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class IngestionRun(Base):
    """Audit trail for every ingestion execution."""

    __tablename__ = "ingestion_runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    data_source_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    dagster_run_id = Column(String(255), nullable=True)
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending|running|completed|failed",
    )
    triggered_by = Column(PG_UUID(as_uuid=True), nullable=True)
    trigger_type = Column(
        String(50),
        nullable=False,
        default="manual",
        comment="manual|scheduled|sensor",
    )
    records_ingested = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_detail = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_ingestion_runs_data_source_id", "data_source_id"),
        Index("ix_ingestion_runs_status", "status"),
        Index("ix_ingestion_runs_started_at", "started_at"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "data_source_id": str(self.data_source_id),
            "dagster_run_id": self.dagster_run_id,
            "status": self.status,
            "triggered_by": str(self.triggered_by) if self.triggered_by else None,
            "trigger_type": self.trigger_type,
            "records_ingested": self.records_ingested,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_detail": self.error_detail,
        }


class DataLineage(Base):
    """Row/asset-level provenance aligned with D4BL methodology."""

    __tablename__ = "data_lineage"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ingestion_run_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_table = Column(String(255), nullable=False)
    record_id = Column(PG_UUID(as_uuid=True), nullable=False)
    source_url = Column(Text, nullable=True)
    source_hash = Column(String(128), nullable=True)
    transformation = Column(JSON, nullable=True)
    quality_score = Column(Float, nullable=True, comment="1-5 scale")
    coverage_metadata = Column(JSON, nullable=True)
    bias_flags = Column(JSON, nullable=True)
    retrieved_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_data_lineage_ingestion_run_id", "ingestion_run_id"),
        Index("ix_data_lineage_target_table", "target_table"),
        Index("ix_data_lineage_record_id", "record_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "ingestion_run_id": str(self.ingestion_run_id),
            "target_table": self.target_table,
            "record_id": str(self.record_id),
            "source_url": self.source_url,
            "source_hash": self.source_hash,
            "transformation": self.transformation,
            "quality_score": self.quality_score,
            "coverage_metadata": self.coverage_metadata,
            "bias_flags": self.bias_flags,
            "retrieved_at": (
                self.retrieved_at.isoformat() if self.retrieved_at else None
            ),
        }


class KeywordMonitor(Base):
    """Topic/keyword-based ingestion configuration."""

    __tablename__ = "keyword_monitors"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    keywords = Column(JSON, nullable=False, default=list)
    source_ids = Column(JSON, nullable=False, default=list)
    schedule = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_keyword_monitors_enabled", "enabled"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "keywords": self.keywords,
            "source_ids": self.source_ids,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CdcHealthOutcome(Base):
    """Health outcomes from CDC PLACES."""
    __tablename__ = "cdc_health_outcomes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(11), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    measure = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    data_value = Column(Float, nullable=False)
    data_value_type = Column(String(50), nullable=False)
    low_confidence_limit = Column(Float, nullable=True)
    high_confidence_limit = Column(Float, nullable=True)
    total_population = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "fips_code", "year", "measure", "data_value_type",
            name="uq_cdc_health_outcome_key",
        ),
        Index("ix_cdc_health_state_measure", "state_fips", "measure", "year"),
    )


class EpaEnvironmentalJustice(Base):
    """Environmental justice screening from EPA EJScreen."""
    __tablename__ = "epa_environmental_justice"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tract_fips = Column(String(11), nullable=False, index=True)
    state_fips = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    indicator = Column(String(200), nullable=False)
    raw_value = Column(Float, nullable=True)
    percentile_state = Column(Float, nullable=True)
    percentile_national = Column(Float, nullable=True)
    demographic_index = Column(Float, nullable=True)
    population = Column(Integer, nullable=True)
    minority_pct = Column(Float, nullable=True)
    low_income_pct = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tract_fips", "year", "indicator",
            name="uq_epa_ej_key",
        ),
        Index("ix_epa_ej_state_indicator", "state_fips", "indicator", "year"),
    )


class FbiCrimeStat(Base):
    """Crime statistics from FBI Crime Data Explorer."""
    __tablename__ = "fbi_crime_stats"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state_abbrev = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    offense = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)
    race = Column(String(100), nullable=True)
    ethnicity = Column(String(50), nullable=True)
    bias_motivation = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    population = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        # Functional unique index is created in migration (handles NULLs
        # via COALESCE); SQLAlchemy UniqueConstraint kept for reference.
        Index(
            "uq_fbi_crime_key",
            "state_abbrev", "offense",
            text("COALESCE(race, '')"),
            text("COALESCE(bias_motivation, '')"),
            "year", "category",
            unique=True,
        ),
        Index("ix_fbi_crime_state_race_year", "state_abbrev", "race", "year"),
    )


class BlsLaborStatistic(Base):
    """Labor statistics from BLS."""
    __tablename__ = "bls_labor_statistics"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    series_id = Column(String(50), nullable=False)
    state_fips = Column(String(2), nullable=True)
    state_name = Column(String(50), nullable=True)
    metric = Column(String(200), nullable=False)
    race = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    period = Column(String(10), nullable=False)
    value = Column(Float, nullable=False)
    footnotes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "series_id", "year", "period",
            name="uq_bls_labor_key",
        ),
        Index("ix_bls_labor_metric_race_year", "metric", "race", "year"),
    )


class HudFairHousing(Base):
    """Fair housing data from HUD."""
    __tablename__ = "hud_fair_housing"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(11), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    indicator = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    value = Column(Float, nullable=False)
    race_group_a = Column(String(50), nullable=True)
    race_group_b = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "fips_code", "year", "indicator", "race_group_a", "race_group_b",
            name="uq_hud_fair_housing_key",
        ),
        Index("ix_hud_fh_state_indicator", "state_fips", "indicator", "year"),
    )


class UsdaFoodAccess(Base):
    """Food access data from USDA."""
    __tablename__ = "usda_food_access"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tract_fips = Column(String(11), nullable=False, index=True)
    state_fips = Column(String(2), nullable=False, index=True)
    county_fips = Column(String(5), nullable=True)
    state_name = Column(String(50), nullable=True)
    county_name = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    indicator = Column(String(200), nullable=False)
    value = Column(Float, nullable=False)
    urban_rural = Column(String(10), nullable=True)
    population = Column(Integer, nullable=True)
    poverty_rate = Column(Float, nullable=True)
    median_income = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tract_fips", "year", "indicator",
            name="uq_usda_food_access_key",
        ),
        Index("ix_usda_fa_state_indicator", "state_fips", "indicator", "year"),
    )


class DoeCivilRights(Base):
    """Civil rights data from DOE CRDC."""
    __tablename__ = "doe_civil_rights"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    district_id = Column(String(20), nullable=False, index=True)
    district_name = Column(Text, nullable=False)
    state = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    school_year = Column(String(9), nullable=False)
    metric = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    race = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    total_enrollment = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "district_id", "school_year", "metric", "race",
            name="uq_doe_civil_rights_key",
        ),
        Index("ix_doe_cr_state_metric_race", "state", "metric", "race"),
    )


class PoliceViolenceIncident(Base):
    """Police violence incidents from Mapping Police Violence."""
    __tablename__ = "police_violence_incidents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id = Column(String(100), nullable=False, unique=True)
    date = Column(Date, nullable=False)
    year = Column(Integer, nullable=False, index=True)
    state = Column(String(2), nullable=False, index=True)
    city = Column(String(200), nullable=True)
    county = Column(String(200), nullable=True)
    race = Column(String(50), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    armed_status = Column(String(100), nullable=True)
    cause_of_death = Column(String(200), nullable=True)
    circumstances = Column(Text, nullable=True)
    criminal_charges = Column(String(200), nullable=True)
    agency = Column(String(200), nullable=True)
    source_url = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        Index("ix_pv_state_race_year", "state", "race", "year"),
    )


class CensusDemographics(Base):
    """Decennial census race/ethnicity population counts."""
    __tablename__ = "census_demographics"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    geo_id = Column(String(11), nullable=False, index=True)
    geo_type = Column(String(10), nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=True)
    county_name = Column(String(200), nullable=True)
    year = Column(Integer, nullable=False)
    race = Column(String(50), nullable=False)
    population = Column(Integer, nullable=True)
    pct_of_total = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("geo_id", "year", "race",
                        name="uq_census_demographics_key"),
        Index("ix_census_demo_state_year", "state_fips", "year"),
    )


class CdcMortality(Base):
    """Mortality data from CDC WONDER / NCHS via SODA API."""
    __tablename__ = "cdc_mortality"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    geo_id = Column(String(20), nullable=False)
    geography_type = Column(String(10), nullable=False)
    state_fips = Column(String(2), nullable=True)
    state_name = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    cause_of_death = Column(String(200), nullable=False)
    race = Column(String(100), nullable=False, default="total")
    deaths = Column(Integer, nullable=True)
    age_adjusted_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "geo_id", "year", "cause_of_death", "race",
            name="uq_cdc_mortality_key",
        ),
        Index("ix_cdc_mortality_state_year", "state_fips", "year", "cause_of_death", "race"),
        Index("ix_cdc_mortality_geo_type", "geography_type", "year"),
    )


class BjsIncarceration(Base):
    """DOJ Bureau of Justice Statistics incarceration data by race."""
    __tablename__ = "bjs_incarceration"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state_abbrev = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=True)
    year = Column(Integer, nullable=False)
    facility_type = Column(String(20), nullable=False)
    metric = Column(String(100), nullable=False)
    race = Column(String(50), nullable=False)
    gender = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("state_abbrev", "year", "facility_type", "metric", "race", "gender",
                        name="uq_bjs_incarceration_key"),
        Index("ix_bjs_inc_state_race_year", "state_abbrev", "race", "year"),
    )


class CongressVote(Base):
    """Congressional voting records from ProPublica."""
    __tablename__ = "congress_votes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    bill_id = Column(String(50), nullable=False)
    bill_number = Column(String(20), nullable=True)
    title = Column(Text, nullable=True)
    subject = Column(String(200), nullable=True)
    congress = Column(Integer, nullable=False)
    chamber = Column(String(10), nullable=False)
    vote_date = Column(Date, nullable=True)
    result = Column(String(50), nullable=True)
    yes_votes = Column(Integer, nullable=True)
    no_votes = Column(Integer, nullable=True)
    topic_tags = Column(JSON, nullable=True)
    url = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("bill_id", "congress", "chamber",
                        name="uq_congress_votes_key"),
        Index("ix_congress_votes_congress_subject", "congress", "subject"),
    )


class VeraIncarceration(Base):
    """Vera Institute county-level incarceration trends by race."""
    __tablename__ = "vera_incarceration"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips = Column(String(5), nullable=False, index=True)
    state = Column(String(2), nullable=False, index=True)
    county_name = Column(String(200), nullable=True)
    year = Column(Integer, nullable=False)
    urbanicity = Column(String(20), nullable=True)
    facility_type = Column(String(20), nullable=False)
    race = Column(String(50), nullable=False)
    population = Column(Integer, nullable=True)
    total_pop = Column(Integer, nullable=True)
    rate_per_100k = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("fips", "year", "facility_type", "race",
                        name="uq_vera_incarceration_key"),
        Index("ix_vera_inc_state_race_year", "state", "race", "year"),
    )


class TrafficStop(Base):
    """Stanford Open Policing Project traffic stop data by race."""
    __tablename__ = "traffic_stops"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state = Column(String(2), nullable=False, index=True)
    county_name = Column(String(200), nullable=True)
    department = Column(String(200), nullable=True)
    year = Column(Integer, nullable=False)
    race = Column(String(50), nullable=False)
    total_stops = Column(Integer, nullable=True)
    search_conducted = Column(Integer, nullable=True)
    contraband_found = Column(Integer, nullable=True)
    arrest_made = Column(Integer, nullable=True)
    citation_issued = Column(Integer, nullable=True)
    search_rate = Column(Float, nullable=True)
    hit_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("state", "department", "year", "race",
                        name="uq_traffic_stops_key"),
        Index("ix_traffic_stops_state_race_year", "state", "race", "year"),
    )


class EvictionData(Base):
    """Eviction Lab eviction rates by geography."""
    __tablename__ = "eviction_data"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    geo_id = Column(String(11), nullable=False, index=True)
    geo_type = Column(String(10), nullable=False)
    state_fips = Column(String(2), nullable=True, index=True)
    geo_name = Column(String(200), nullable=True)
    year = Column(Integer, nullable=False)
    population = Column(Integer, nullable=True)
    poverty_rate = Column(Float, nullable=True)
    pct_renter_occupied = Column(Float, nullable=True)
    median_gross_rent = Column(Float, nullable=True)
    eviction_filings = Column(Integer, nullable=True)
    evictions = Column(Integer, nullable=True)
    eviction_rate = Column(Float, nullable=True)
    eviction_filing_rate = Column(Float, nullable=True)
    pct_nonwhite = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("geo_id", "year",
                        name="uq_eviction_data_key"),
        Index("ix_eviction_data_state_year", "state_fips", "year"),
    )


# Database connection setup
def get_database_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    db_user = settings.postgres_user
    db_password = settings.postgres_password
    db_host = settings.postgres_host
    db_port = settings.postgres_port
    db_name = settings.postgres_db

    if db_host in ("localhost", "127.0.0.1") and settings.is_docker:
        original_host = db_host
        db_host = "postgres"
        print(
            f"⚠ Warning: Detected Docker environment, "
            f"using 'postgres' as hostname instead of '{original_host}'"
        )
    elif db_host in ("localhost", "127.0.0.1"):
        print(
            "⚠ Warning: Using 'localhost' as database host. "
            "In Docker, this should be 'postgres' or 'host.docker.internal'"
        )

    if not db_name or db_name == db_user:
        db_name = "postgres"
        print(f"⚠ Warning: Using default database name: {db_name}")

    database_url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    print(f"📊 Database URL: postgresql+asyncpg://{db_user}:***@{db_host}:{db_port}/{db_name}")

    return database_url


# Create async engine
engine = None
async_session_maker = None


def init_db():
    """Initialize database connection"""
    global engine, async_session_maker

    settings = get_settings()
    database_url = get_database_url()
    engine = create_async_engine(
        database_url,
        echo=settings.db_echo,
        future=True,
        pool_pre_ping=True,  # Verify connections before using them
        pool_size=5,  # Limit connection pool size
        max_overflow=10,  # Max overflow connections
        pool_recycle=3600,  # Recycle connections after 1 hour
    )
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    """Get database session"""
    if async_session_maker is None:
        init_db()
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """Create all database tables"""
    if engine is None:
        init_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connection"""
    if engine:
        await engine.dispose()


# Import StateSummary so it is registered with Base.metadata
from d4bl.infra.state_summary import StateSummary  # noqa: E402, F401

