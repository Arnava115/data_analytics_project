-- Fail if the query returns any rows.

SELECT 'mart.city_day is empty' AS failure
WHERE (SELECT COUNT(*) FROM mart.city_day) = 0
UNION ALL
SELECT 'mart.zone_hour is empty' AS failure
WHERE (SELECT COUNT(*) FROM mart.zone_hour) = 0
UNION ALL
SELECT 'mart.borough_week is empty' AS failure
WHERE (SELECT COUNT(*) FROM mart.borough_week) = 0
UNION ALL
SELECT 'dim.zones is empty' AS failure
WHERE (SELECT COUNT(*) FROM dim.zones) = 0;
