SELECT
    t.pickup_date,
    t.week_start,
    t.platform,
    COUNT(*) AS trips,
    SUM(t.passenger_fare) AS passenger_fare_sum,
    SUM(t.driver_pay) AS driver_pay_sum,
    SUM(t.tips) AS tips_sum,
    SUM(t.trip_miles) AS miles_sum,
    SUM(t.trip_time_seconds) AS trip_time_seconds_sum,
    SUM(CASE WHEN t.wait_seconds IS NOT NULL THEN t.wait_seconds ELSE 0 END) AS wait_seconds_sum,
    COUNT(t.wait_seconds) AS wait_trips,
    SUM(CASE WHEN pu.is_airport OR COALESCE(doz.is_airport, FALSE) THEN 1 ELSE 0 END) AS airport_trips,
    SUM(CASE WHEN t.shared_match_flag = 'Y' THEN 1 ELSE 0 END) AS shared_match_trips,
    SUM(CASE WHEN t.shared_request_flag = 'Y' THEN 1 ELSE 0 END) AS shared_request_trips,
    SUM(CASE WHEN t.is_weekend THEN 1 ELSE 0 END) AS weekend_trips,
    SUM(CASE WHEN t.is_night THEN 1 ELSE 0 END) AS night_trips,
    COUNT(DISTINCT t.pu_location_id) AS unique_pickup_zones,
    approx_quantile(t.trip_time_seconds, 0.5) AS trip_time_p50_seconds,
    approx_quantile(t.trip_time_seconds, 0.9) AS trip_time_p90_seconds,
    approx_quantile(t.wait_seconds, 0.5) AS wait_p50_seconds,
    approx_quantile(t.wait_seconds, 0.9) AS wait_p90_seconds
FROM stg.trips t
INNER JOIN dim.zones pu ON pu.location_id = t.pu_location_id
LEFT JOIN dim.zones doz ON doz.location_id = t.do_location_id
GROUP BY t.pickup_date, t.week_start, t.platform
