"""Ingestion runner — executes ingestion scripts as async background tasks.

Executes ingestion scripts as direct in-process async background tasks.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

# ---------------------------------------------------------------------------
# Script registry — single source of truth for source slug → module mapping.
# The module names correspond to files under scripts/ingestion/.
# ---------------------------------------------------------------------------

SCRIPT_REGISTRY: dict[str, str] = {
    "cdc": "ingest_cdc_places",
    "cdc_places": "ingest_cdc_places",
    "cdc_mortality": "ingest_cdc_mortality",
    "cdc_mort": "ingest_cdc_mortality",
    "census": "ingest_census_acs",
    "census_acs": "ingest_census_acs",
    "census_decennial": "ingest_census_demographics",
    "census_demographics": "ingest_census_demographics",
    "epa": "ingest_epa_ejscreen",
    "epa_ejscreen": "ingest_epa_ejscreen",
    "fbi": "ingest_fbi_ucr",
    "fbi_ucr": "ingest_fbi_ucr",
    "bls": "ingest_bls_labor",
    "bls_labor": "ingest_bls_labor",
    "hud": "ingest_hud_housing",
    "hud_housing": "ingest_hud_housing",
    "usda": "ingest_usda_food",
    "usda_food": "ingest_usda_food",
    "doe": "ingest_doe_education",
    "doe_education": "ingest_doe_education",
    "police": "ingest_police_violence",
    "police_violence": "ingest_police_violence",
    "openstates": "ingest_openstates",
    "bjs": "ingest_bjs_incarceration",
    "bjs_incarceration": "ingest_bjs_incarceration",
    # Web content sources (Sprint 2)
    "rss": "ingest_rss_feeds",
    "rss_feeds": "ingest_rss_feeds",
    "web": "ingest_web_sources",
    "web_scrape": "ingest_web_sources",
    "news": "ingest_news_search",
    "news_search": "ingest_news_search",
    # New data sources (Sprint 2)
    "county_health": "ingest_county_health_rankings",
    "chr": "ingest_county_health_rankings",
    "usaspending": "ingest_usaspending",
    "vera": "ingest_vera_incarceration",
    "vera_incarceration": "ingest_vera_incarceration",
}

logger = logging.getLogger(__name__)

# Ensure scripts/ is on sys.path for `import ingestion.ingest_xxx`
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def slugify(name: str) -> str:
    """Convert a source name to a registry-compatible slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def resolve_source(name: str) -> str | None:
    """Look up a DataSource name in the registry, returning the module name or None."""
    if not name:
        return None
    slug = slugify(name)
    return SCRIPT_REGISTRY.get(slug)


def _import_script(module_name: str):
    """Import an ingestion script module by name."""
    return importlib.import_module(f"ingestion.{module_name}")


async def run_ingestion_task(
    run_id: UUID,
    module_name: str,
    session_factory,
) -> None:
    """Background task: run an ingestion script and update the IngestionRun row."""
    from d4bl.infra.database import IngestionRun

    async with session_factory() as session:
        result = await session.execute(select(IngestionRun).where(IngestionRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            logger.error("IngestionRun %s not found, aborting task", run_id)
            return

        run.status = "running"
        await session.commit()

        try:
            module = _import_script(module_name)
            records = await asyncio.to_thread(module.main)
            run.status = "completed"
            run.records_ingested = records if records is not None else 0
        except Exception as exc:
            logger.exception("Ingestion script %s failed for run %s", module_name, run_id)
            run.status = "failed"
            run.error_detail = str(exc)

        run.completed_at = datetime.now(timezone.utc)
        await session.commit()
