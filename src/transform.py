from __future__ import annotations

import logging
from datetime import datetime, timezone

import duckdb

from src.config import DB_PATH, SQL_DIR, WAREHOUSE_DIR, ensure_dirs, load_config
from src.ingest import ZONE_LOOKUP_PATH
from src.metrics import KPI_ROLLUP_SELECT

log = logging.getLogger("citypulse.transform")


def connect(*, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    ensure_dirs()
    cfg = load_config()
    db = duckdb.connect(str(DB_PATH), read_only=read_only)
    if not read_only:
        duck = cfg.get("duckdb", {})
        db.execute(f"PRAGMA memory_limit='{duck.get('memory_limit', '4GB')}'")
        db.execute(f"PRAGMA threads={int(duck.get('threads', 4))}")
        db.execute("PRAGMA preserve_insertion_order=false")
    return db


def _sql_file(relative: str) -> str:
    return (SQL_DIR / relative).read_text()


def _render(sql: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        sql = sql.replace(key, value)
    return sql


def _junk_mapping(parquet_path: str, year_month: str) -> dict[str, str]:
    cfg = load_config()
    junk = cfg["junk"]
    airports = cfg["airports"]
    return {
        "__PARQUET_PATH__": parquet_path.replace("'", "''"),
        "__ZONE_LOOKUP_PATH__": str(ZONE_LOOKUP_PATH).replace("'", "''"),
        "__AIRPORT_IDS__": ", ".join(str(int(k)) for k in airports),
        "__MIN_LOC__": str(int(junk["min_location_id"])),
        "__MAX_LOC__": str(int(junk["max_location_id"])),
        "__MAX_MILES__": str(float(junk["max_trip_miles"])),
        "__MAX_TRIP_SECONDS__": str(int(junk["max_trip_seconds"])),
        "__MAX_WAIT__": str(int(junk["max_wait_seconds"])),
        "__MAX_FARE__": str(float(junk["max_passenger_fare"])),
        "__YEAR_MONTH__": year_month,
        "__MONTH_START__": f"{year_month}-01",
    }


def _write_kpi_views(con: duckdb.DuckDBPyConnection) -> None:
    grains = {
        "city_day_kpis": "mart.city_day",
        "zone_hour_kpis": "mart.zone_hour",
        "borough_week_kpis": "mart.borough_week",
    }
    for view, table in grains.items():
        con.execute(
            f"""
            CREATE OR REPLACE VIEW mart.{view} AS
            SELECT
                src.*,
                (src.passenger_fare_sum - src.driver_pay_sum)
                    / NULLIF(src.passenger_fare_sum, 0) AS take_rate,
                src.miles_sum / NULLIF(src.trips, 0) AS avg_trip_miles,
                (src.trip_time_seconds_sum / NULLIF(src.trips, 0)) / 60.0 AS avg_trip_minutes,
                (src.wait_seconds_sum / NULLIF(src.wait_trips, 0)) / 60.0 AS avg_wait_minutes,
                src.airport_trips::DOUBLE / NULLIF(src.trips, 0) AS airport_share,
                src.shared_match_trips::DOUBLE / NULLIF(src.trips, 0) AS shared_match_rate,
                src.driver_pay_sum / NULLIF(src.trip_time_seconds_sum / 3600.0, 0) AS driver_pay_per_hour,
                src.tips_sum / NULLIF(src.passenger_fare_sum, 0) AS tip_rate,
                src.passenger_fare_sum / NULLIF(src.trips, 0) AS avg_passenger_fare,
                src.driver_pay_sum / NULLIF(src.trips, 0) AS avg_driver_pay,
                (src.wait_p50_seconds / 60.0) AS wait_p50_minutes,
                (src.wait_p90_seconds / 60.0) AS wait_p90_minutes,
                (src.trip_time_p50_seconds / 60.0) AS trip_time_p50_minutes,
                (src.trip_time_p90_seconds / 60.0) AS trip_time_p90_minutes
            FROM {table} src
            """
        )
    log.info("KPI views ready (rollup fragment is %s chars)", len(KPI_ROLLUP_SELECT))


def init_warehouse() -> None:
    """Create schemas, dim.zones, and empty marts."""
    if not ZONE_LOOKUP_PATH.exists():
        raise FileNotFoundError(f"Missing zone lookup at {ZONE_LOOKUP_PATH}")
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    mapping = _junk_mapping("", "1970-01")
    con = connect(read_only=False)
    try:
        con.execute(_render(_sql_file("staging/00_raw_and_dim.sql"), mapping))
        for table in ("zone_hour", "city_day", "borough_week"):
            con.execute(f"DROP TABLE IF EXISTS mart.{table}")
        con.execute("DROP TABLE IF EXISTS meta.ingest_profile")
        con.execute("DROP TABLE IF EXISTS meta.ingest_profile_parts")
        con.execute("DROP TABLE IF EXISTS meta.pipeline_run")
        con.execute(
            """
            CREATE TABLE meta.ingest_profile_parts (
                year_month VARCHAR,
                rows_in_scope BIGINT,
                junk_rows BIGINT,
                min_pickup_at TIMESTAMP,
                max_pickup_at TIMESTAMP
            )
            """
        )
        log.info("Warehouse initialized with %s taxi zones", con.execute("SELECT COUNT(*) FROM dim.zones").fetchone()[0])
    finally:
        con.close()


def transform_month(parquet_path: str, year_month: str, *, first: bool) -> dict:
    """Scan one monthly parquet into zone-hour and city-day marts. No trip-level table."""
    mapping = _junk_mapping(parquet_path, year_month)
    con = connect(read_only=False)
    try:
        log.info("Staging %s from %s", year_month, parquet_path)
        con.execute(_render(_sql_file("staging/01_stg_trips.sql"), mapping))
        profile = con.execute("SELECT * FROM meta.month_profile").fetchdf().iloc[0].to_dict()
        con.execute(
            """
            INSERT INTO meta.ingest_profile_parts
            SELECT year_month, rows_in_scope, junk_rows, min_pickup_at, max_pickup_at
            FROM meta.month_profile
            """
        )
        log.info(
            "%s in-scope=%s junk=%s (%.1f%%)",
            year_month,
            f"{int(profile['rows_in_scope']):,}",
            f"{int(profile['junk_rows']):,}",
            100 * profile["junk_rows"] / max(profile["rows_in_scope"], 1),
        )
        zh = _sql_file("marts/01_zone_hour.sql")
        cd = _sql_file("marts/02_city_day.sql")
        if first:
            log.info("Creating mart.zone_hour and mart.city_day")
            con.execute(f"CREATE TABLE mart.zone_hour AS {zh}")
            con.execute(f"CREATE TABLE mart.city_day AS {cd}")
        else:
            log.info("Appending %s into marts", year_month)
            con.execute(f"INSERT INTO mart.zone_hour {zh}")
            con.execute(f"INSERT INTO mart.city_day {cd}")
        return profile
    finally:
        con.close()


def finalize() -> dict:
    """Borough-week rollup, demand deciles, KPI views, run metadata."""
    con = connect(read_only=False)
    try:
        log.info("Building mart.borough_week from zone-hour")
        con.execute(f"CREATE OR REPLACE TABLE mart.borough_week AS {_sql_file('marts/03_borough_week.sql')}")
        log.info("Adding demand deciles")
        con.execute(
            """
            CREATE OR REPLACE TABLE mart.zone_hour_decile AS
            SELECT
                z.*,
                NTILE(10) OVER (
                    PARTITION BY platform, pickup_hour
                    ORDER BY trips
                ) AS demand_decile
            FROM mart.zone_hour z
            """
        )
        con.execute("DROP TABLE mart.zone_hour")
        con.execute("ALTER TABLE mart.zone_hour_decile RENAME TO zone_hour")
        _write_kpi_views(con)
        con.execute(
            """
            CREATE OR REPLACE TABLE meta.ingest_profile AS
            SELECT
                SUM(rows_in_scope) AS rows_in_scope,
                SUM(junk_rows) AS junk_rows,
                MIN(min_pickup_at) AS min_pickup_at,
                MAX(max_pickup_at) AS max_pickup_at
            FROM meta.ingest_profile_parts
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TABLE meta.pipeline_run AS
            SELECT
                ?::TIMESTAMP AS ran_at_utc,
                (SELECT COUNT(*) FROM meta.ingest_profile_parts) AS parquet_files,
                0::BIGINT AS stg_trips_rows,
                (SELECT rows_in_scope FROM meta.ingest_profile) AS rows_in_scope,
                (SELECT junk_rows FROM meta.ingest_profile) AS junk_rows,
                (SELECT COUNT(*) FROM mart.city_day) AS city_day_rows,
                (SELECT COUNT(*) FROM mart.zone_hour) AS zone_hour_rows,
                (SELECT MIN(pickup_date) FROM mart.city_day) AS min_date,
                (SELECT MAX(pickup_date) FROM mart.city_day) AS max_date
            """,
            [datetime.now(timezone.utc).replace(tzinfo=None)],
        )
        summary = con.execute("SELECT * FROM meta.pipeline_run").fetchdf().iloc[0].to_dict()
        log.info("Transform complete: %s", summary)
        return summary
    finally:
        con.close()


def transform(parquet_paths: list[str] | None = None) -> dict:
    """Back-compat: build the whole warehouse from a list of local parquet files."""
    from pathlib import Path

    from src.ingest import RAW_DIR

    if parquet_paths is None:
        parquet_paths = sorted(str(p) for p in RAW_DIR.glob("fhvhv_tripdata_*.parquet"))
    if not parquet_paths:
        raise FileNotFoundError("No FHVHV parquet files in data/raw. Run ingest first.")
    init_warehouse()
    for i, path in enumerate(parquet_paths):
        name = Path(path).name
        year_month = name.replace("fhvhv_tripdata_", "").replace(".parquet", "")
        transform_month(path, year_month, first=(i == 0))
    return finalize()
