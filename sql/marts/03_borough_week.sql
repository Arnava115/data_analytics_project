-- Built from zone-hour after all months are loaded so ISO weeks that span months stay correct.
-- Quantiles are not roll-up-safe; they stay NULL here. Use zone-hour / city-day for p50/p90.

SELECT
    week_start,
    borough,
    platform,
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
    COUNT(DISTINCT pu_location_id) AS unique_pickup_zones,
    NULL::DOUBLE AS trip_time_p50_seconds,
    NULL::DOUBLE AS trip_time_p90_seconds,
    NULL::DOUBLE AS wait_p50_seconds,
    NULL::DOUBLE AS wait_p90_seconds
FROM mart.zone_hour
GROUP BY week_start, borough, platform
