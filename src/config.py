from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REF_DIR = DATA_DIR / "reference"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
DB_PATH = WAREHOUSE_DIR / "city_pulse.duckdb"

TLC_TRIP_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/fhvhv_tripdata_{year_month}.parquet"
ZONE_LOOKUP_URLS = [
    "https://d37ci6vzurychx.cloudfront.net/misc/taxi+_zone_lookup.csv",
    "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv",
]
TAXI_ZONES_ZIP_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def ensure_dirs() -> None:
    for path in (RAW_DIR, REF_DIR, WAREHOUSE_DIR):
        path.mkdir(parents=True, exist_ok=True)
