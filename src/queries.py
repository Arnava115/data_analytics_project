"""Dashboard queries. Rates are always recomputed from sums (see src/metrics.py)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.metrics import KPI_ROLLUP_SELECT
from src.transform import connect


@dataclass
class Filters:
    start: date
    end: date
    platform: str
    boroughs: list[str]
    time_of_day: list[str]
    airport: str  # all | airport | street


def warehouse_bounds() -> dict:
    con = connect(read_only=True)
    try:
        row = con.execute(
            """
            SELECT
                MIN(pickup_date) AS min_date,
                MAX(pickup_date) AS max_date,
                (SELECT ran_at_utc FROM meta.pipeline_run) AS ran_at_utc
            FROM mart.city_day
            """
        ).fetchone()
        boroughs = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT borough FROM dim.zones WHERE borough IS NOT NULL ORDER BY 1"
            ).fetchall()
        ]
    finally:
        con.close()
    return {"min_date": row[0], "max_date": row[1], "ran_at_utc": row[2], "boroughs": boroughs}


def _where(filters: Filters, alias: str = "") -> tuple[str, list]:
    p = f"{alias}." if alias else ""
    clauses = [
        f"{p}pickup_date BETWEEN ? AND ?",
        f"{p}platform = ?",
    ]
    params: list = [filters.start, filters.end, filters.platform]
    if filters.boroughs:
        placeholders = ", ".join("?" for _ in filters.boroughs)
        clauses.append(f"{p}borough IN ({placeholders})")
        params.extend(filters.boroughs)
    if filters.time_of_day:
        placeholders = ", ".join("?" for _ in filters.time_of_day)
        clauses.append(f"{p}time_of_day IN ({placeholders})")
        params.extend(filters.time_of_day)
    if filters.airport == "airport":
        clauses.append(f"{p}pu_is_airport")
    elif filters.airport == "street":
        clauses.append(f"NOT {p}pu_is_airport")
    return " AND ".join(clauses), params


def rollup_city_day(filters: Filters) -> pd.DataFrame:
    where, params = _where(filters)
    sql = f"""
        SELECT
            pickup_date,
            {KPI_ROLLUP_SELECT}
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY pickup_date
        ORDER BY pickup_date
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def rollup_totals(filters: Filters) -> dict:
    where, params = _where(filters)
    sql = f"""
        SELECT {KPI_ROLLUP_SELECT}
        FROM mart.zone_hour
        WHERE {where}
    """
    con = connect(read_only=True)
    try:
        df = con.execute(sql, params).fetchdf()
        return df.iloc[0].to_dict() if not df.empty else {}
    finally:
        con.close()


def rollup_hour(filters: Filters) -> pd.DataFrame:
    where, params = _where(filters)
    sql = f"""
        SELECT
            pickup_hour,
            {KPI_ROLLUP_SELECT}
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY pickup_hour
        ORDER BY pickup_hour
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def rollup_borough(filters: Filters) -> pd.DataFrame:
    where, params = _where(filters)
    sql = f"""
        SELECT
            borough,
            {KPI_ROLLUP_SELECT}
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY borough
        ORDER BY trips DESC
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def rollup_zone(filters: Filters, limit: int = 25) -> pd.DataFrame:
    where, params = _where(filters)
    sql = f"""
        SELECT
            pu_location_id,
            ANY_VALUE(zone_name) AS zone_name,
            ANY_VALUE(borough) AS borough,
            MAX(demand_decile) AS demand_decile,
            {KPI_ROLLUP_SELECT},
            AVG(wait_p90_seconds) / 60.0 AS wait_p90_minutes,
            AVG(trip_time_p90_seconds) / 60.0 AS trip_time_p90_minutes
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY pu_location_id
        ORDER BY trips DESC
        LIMIT {int(limit)}
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def zone_hour_heatmap(filters: Filters, top_n: int = 20) -> pd.DataFrame:
    """Top N zones by trips, then hour mix — for the supply heatmap."""
    where, params = _where(filters)
    sql = f"""
        WITH top_zones AS (
            SELECT pu_location_id
            FROM mart.zone_hour
            WHERE {where}
            GROUP BY pu_location_id
            ORDER BY SUM(trips) DESC
            LIMIT {int(top_n)}
        )
        SELECT
            z.zone_name,
            z.pickup_hour,
            SUM(z.trips) AS trips,
            (SUM(z.wait_seconds_sum) / NULLIF(SUM(z.wait_trips), 0)) / 60.0 AS avg_wait_minutes
        FROM mart.zone_hour z
        INNER JOIN top_zones t ON t.pu_location_id = z.pu_location_id
        WHERE {where}
        GROUP BY z.zone_name, z.pickup_hour
    """
    con = connect(read_only=True)
    try:
        # params used twice
        return con.execute(sql, params + params).fetchdf()
    finally:
        con.close()


def borough_hour_heatmap(filters: Filters) -> pd.DataFrame:
    where, params = _where(filters)
    sql = f"""
        SELECT
            borough,
            pickup_hour,
            SUM(trips) AS trips
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY borough, pickup_hour
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def coverage_gaps(filters: Filters, peak_hours: tuple[int, ...] = (7, 8, 9, 17, 18, 19)) -> pd.DataFrame:
    """Zones in the bottom quartile of volume during city peak hours."""
    where, params = _where(filters)
    hour_list = ", ".join(str(int(h)) for h in peak_hours)
    sql = f"""
        WITH peak AS (
            SELECT
                pu_location_id,
                ANY_VALUE(zone_name) AS zone_name,
                ANY_VALUE(borough) AS borough,
                SUM(trips) AS peak_trips,
                (SUM(wait_seconds_sum) / NULLIF(SUM(wait_trips), 0)) / 60.0 AS avg_wait_minutes
            FROM mart.zone_hour
            WHERE {where}
              AND pickup_hour IN ({hour_list})
            GROUP BY pu_location_id
        ),
        stats AS (
            SELECT quantile_cont(peak_trips, 0.25) AS q25 FROM peak
        )
        SELECT p.*
        FROM peak p, stats s
        WHERE p.peak_trips <= s.q25
        ORDER BY p.peak_trips ASC
        LIMIT 20
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def competitor_overlay(filters: Filters) -> pd.DataFrame:
    """Uber vs Lyft on the same date/geo/time filters."""
    clauses = ["pickup_date BETWEEN ? AND ?"]
    params: list = [filters.start, filters.end]
    if filters.boroughs:
        placeholders = ", ".join("?" for _ in filters.boroughs)
        clauses.append(f"borough IN ({placeholders})")
        params.extend(filters.boroughs)
    if filters.time_of_day:
        placeholders = ", ".join("?" for _ in filters.time_of_day)
        clauses.append(f"time_of_day IN ({placeholders})")
        params.extend(filters.time_of_day)
    if filters.airport == "airport":
        clauses.append("pu_is_airport")
    elif filters.airport == "street":
        clauses.append("NOT pu_is_airport")
    where = " AND ".join(clauses)
    sql = f"""
        SELECT
            pickup_date,
            platform,
            {KPI_ROLLUP_SELECT}
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY pickup_date, platform
        ORDER BY pickup_date, platform
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def all_zones_for_map(filters: Filters) -> pd.DataFrame:
    where, params = _where(filters)
    sql = f"""
        SELECT
            pu_location_id,
            ANY_VALUE(zone_name) AS zone_name,
            ANY_VALUE(borough) AS borough,
            {KPI_ROLLUP_SELECT},
            (SUM(wait_seconds_sum) / NULLIF(SUM(wait_trips), 0)) / 60.0 AS avg_wait_minutes
        FROM mart.zone_hour
        WHERE {where}
        GROUP BY pu_location_id
    """
    con = connect(read_only=True)
    try:
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()
