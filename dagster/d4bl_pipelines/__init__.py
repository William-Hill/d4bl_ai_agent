import logging

from dagster import Definitions, load_assets_from_modules

from d4bl_pipelines import assets as asset_modules
from d4bl_pipelines.resources import get_db_url, get_resources
from d4bl_pipelines.schedules import load_schedules_from_db

logger = logging.getLogger(__name__)

all_assets = load_assets_from_modules([asset_modules])

try:
    schedules = load_schedules_from_db(get_db_url())
except Exception:
    logger.warning("Failed to load schedules from DB; starting with none")
    schedules = []

defs = Definitions(
    assets=all_assets,
    resources=get_resources(),
    schedules=schedules,
)
