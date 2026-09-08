"""Single source of truth for KPI rollup SQL.

Grain tables store sums/counts. Dashboards and views must recompute rates from
these fragments so take rate on a filter is not the average of take rates.
"""

from __future__ import annotations

# Used by mart KPI views and by app rollups over mart.zone_hour.
KPI_ROLLUP_SELECT = """
    SUM(trips) AS trips,
    SUM(passenger_fare_sum) AS passenger_fare_sum,
    SUM(driver_pay_sum) AS driver_pay_sum,
    SUM(tips_sum) AS tips_sum,
    SUM(miles_sum) AS miles_sum,
    SUM(trip_time_seconds_sum) AS trip_time_seconds_sum,
    SUM(wait_seconds_sum) AS wait_seconds_sum,
    SUM(wait_trips) AS wait_trips,
    SUM(airport_trips) AS airport_trips,
    SUM(shared_match_trips) AS shared_match_trips,
    SUM(shared_request_trips) AS shared_request_trips,
    SUM(weekend_trips) AS weekend_trips,
    SUM(night_trips) AS night_trips,
    (SUM(passenger_fare_sum) - SUM(driver_pay_sum))
        / NULLIF(SUM(passenger_fare_sum), 0) AS take_rate,
    SUM(miles_sum) / NULLIF(SUM(trips), 0) AS avg_trip_miles,
    (SUM(trip_time_seconds_sum) / NULLIF(SUM(trips), 0)) / 60.0 AS avg_trip_minutes,
    (SUM(wait_seconds_sum) / NULLIF(SUM(wait_trips), 0)) / 60.0 AS avg_wait_minutes,
    SUM(airport_trips)::DOUBLE / NULLIF(SUM(trips), 0) AS airport_share,
    SUM(shared_match_trips)::DOUBLE / NULLIF(SUM(trips), 0) AS shared_match_rate,
    SUM(driver_pay_sum) / NULLIF(SUM(trip_time_seconds_sum) / 3600.0, 0) AS driver_pay_per_hour,
    SUM(tips_sum) / NULLIF(SUM(passenger_fare_sum), 0) AS tip_rate,
    SUM(passenger_fare_sum) / NULLIF(SUM(trips), 0) AS avg_passenger_fare,
    SUM(driver_pay_sum) / NULLIF(SUM(trips), 0) AS avg_driver_pay
"""

# Quantiles cannot be rolled up. Keep them only on grain tables built from trips.
GRAIN_QUANTILE_SELECT = """
    quantile_cont(trip_time_seconds, 0.5) AS trip_time_p50_seconds,
    quantile_cont(trip_time_seconds, 0.9) AS trip_time_p90_seconds,
    quantile_cont(wait_seconds, 0.5) FILTER (WHERE wait_seconds IS NOT NULL) AS wait_p50_seconds,
    quantile_cont(wait_seconds, 0.9) FILTER (WHERE wait_seconds IS NOT NULL) AS wait_p90_seconds
"""
