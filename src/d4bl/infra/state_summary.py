"""Pre-aggregated state-level summaries for explore page performance."""

from sqlalchemy import Column, Float, Integer, String, UniqueConstraint

from d4bl.infra.database import Base


class StateSummary(Base):
    """Pre-aggregated state-level metrics from tract/district data.

    Populated during ingestion to avoid expensive on-the-fly aggregation
    of tract-level EPA, USDA, Census, and DOE data.
    """

    __tablename__ = "state_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)
    state_fips = Column(String(2), nullable=False, index=True)
    state_name = Column(String(100), nullable=False)
    metric = Column(String(200), nullable=False)
    race = Column(String(50), nullable=False, default="total")
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source",
            "state_fips",
            "metric",
            "race",
            "year",
            name="uq_state_summary_source_state_metric_race_year",
        ),
    )
