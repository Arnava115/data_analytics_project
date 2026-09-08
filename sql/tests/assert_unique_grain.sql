SELECT 'duplicate city_day grain' AS failure
FROM mart.city_day
GROUP BY pickup_date, platform
HAVING COUNT(*) > 1
UNION ALL
SELECT 'duplicate zone_hour grain' AS failure
FROM mart.zone_hour
GROUP BY pickup_date, pickup_hour, pu_location_id, platform
HAVING COUNT(*) > 1
UNION ALL
SELECT 'duplicate borough_week grain' AS failure
FROM mart.borough_week
GROUP BY week_start, borough, platform
HAVING COUNT(*) > 1;
