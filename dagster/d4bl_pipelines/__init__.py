import logging

from d4bl_pipelines import assets as asset_modules
from d4bl_pipelines.resources import get_db_url, get_resources
from d4bl_pipelines.schedules import build_static_schedules, load_schedules_from_db
from dagster import Definitions, load_assets_from_modules

logger = logging.getLogger(__name__)

all_assets = load_assets_from_modules([asset_modules])

static_schedules = build_static_schedules()

try:
    db_schedules = load_schedules_from_db(get_db_url())
except Exception:
    logger.warning(
        "Failed to load schedules from DB; starting with none",
        exc_info=True,
    )
    db_schedules = []

schedules = static_schedules + db_schedules

defs = Definitions(
    assets=all_assets,
    resources=get_resources(),
    schedules=schedules,
)
