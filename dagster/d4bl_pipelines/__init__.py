from dagster import Definitions, load_assets_from_modules

from d4bl_pipelines import assets as asset_modules
from d4bl_pipelines.resources import get_resources

all_assets = load_assets_from_modules([asset_modules])

defs = Definitions(
    assets=all_assets,
    resources=get_resources(),
)
