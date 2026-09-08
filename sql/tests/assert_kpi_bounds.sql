SELECT 'city_day trips <= 0' AS failure
FROM mart.city_day
WHERE trips <= 0
UNION ALL
SELECT 'take rate out of bounds on city_day' AS failure
FROM mart.city_day_kpis
WHERE take_rate IS NULL
   OR take_rate < -0.5
   OR take_rate > 0.9
UNION ALL
SELECT 'airport share out of bounds' AS failure
FROM mart.city_day_kpis
WHERE airport_share < 0 OR airport_share > 1
UNION ALL
SELECT 'wait minutes out of bounds' AS failure
FROM mart.city_day_kpis
WHERE avg_wait_minutes IS NOT NULL
  AND (avg_wait_minutes < 0 OR avg_wait_minutes > 120)
UNION ALL
SELECT 'driver pay per hour non-positive' AS failure
FROM mart.city_day_kpis
WHERE driver_pay_per_hour IS NULL OR driver_pay_per_hour <= 0
UNION ALL
SELECT 'zone_hour unknown pickup zone' AS failure
FROM mart.zone_hour z
LEFT JOIN dim.zones d ON d.location_id = z.pu_location_id
WHERE d.location_id IS NULL
UNION ALL
SELECT 'junk rate above 15%' AS failure
FROM meta.ingest_profile
WHERE junk_rows::DOUBLE / NULLIF(rows_in_scope, 0) > 0.15
UNION ALL
SELECT 'future pickup dates' AS failure
FROM mart.city_day
WHERE pickup_date > CURRENT_DATE;
