CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dim;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS meta;

CREATE OR REPLACE TABLE dim.zones AS
SELECT
    CAST(LocationID AS INTEGER) AS location_id,
    TRIM(Borough) AS borough,
    TRIM(Zone) AS zone_name,
    TRIM(service_zone) AS service_zone,
    CAST(LocationID AS INTEGER) IN (__AIRPORT_IDS__) AS is_airport,
    CASE CAST(LocationID AS INTEGER)
        WHEN 1 THEN 'EWR'
        WHEN 132 THEN 'JFK'
        WHEN 138 THEN 'LGA'
        ELSE NULL
    END AS airport_code
FROM read_csv_auto('__ZONE_LOOKUP_PATH__', header=true)
WHERE LocationID IS NOT NULL;
