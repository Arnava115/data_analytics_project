-- One calendar month at a time. raw.trips is a view over a single parquet file.

CREATE OR REPLACE VIEW raw.trips AS
SELECT *
FROM read_parquet('__PARQUET_PATH__', union_by_name=true, hive_partitioning=false);

CREATE OR REPLACE TABLE meta.month_profile AS
WITH src AS (
    SELECT
        request_datetime,
        pickup_datetime,
        dropoff_datetime,
        CAST(PULocationID AS INTEGER) AS pu_location_id,
        CAST(DOLocationID AS INTEGER) AS do_location_id,
        CAST(trip_miles AS DOUBLE) AS trip_miles,
        CAST(trip_time AS BIGINT) AS trip_time_seconds,
        CAST(base_passenger_fare AS DOUBLE) AS passenger_fare,
        CAST(driver_pay AS DOUBLE) AS driver_pay,
        DATE_DIFF('second', request_datetime, pickup_datetime) AS wait_seconds
    FROM raw.trips
    WHERE hvfhs_license_num IN ('HV0003', 'HV0005')
      AND date_trunc('month', pickup_datetime) = DATE '__MONTH_START__'
)
SELECT
    '__YEAR_MONTH__' AS year_month,
    COUNT(*) AS rows_in_scope,
    COUNT(*) FILTER (
        WHERE pickup_datetime IS NULL
           OR dropoff_datetime IS NULL
           OR pickup_datetime >= dropoff_datetime
           OR pu_location_id IS NULL
           OR do_location_id IS NULL
           OR pu_location_id < __MIN_LOC__
           OR pu_location_id > __MAX_LOC__
           OR do_location_id < __MIN_LOC__
           OR do_location_id > __MAX_LOC__
           OR trip_miles IS NULL OR trip_miles <= 0 OR trip_miles > __MAX_MILES__
           OR trip_time_seconds IS NULL
           OR trip_time_seconds <= 0
           OR trip_time_seconds > __MAX_TRIP_SECONDS__
           OR passenger_fare IS NULL
           OR passenger_fare <= 0
           OR passenger_fare > __MAX_FARE__
           OR driver_pay IS NULL
           OR driver_pay < 0
           OR (
                wait_seconds IS NOT NULL
                AND (wait_seconds < 0 OR wait_seconds > __MAX_WAIT__)
              )
    ) AS junk_rows,
    MIN(pickup_datetime) AS min_pickup_at,
    MAX(pickup_datetime) AS max_pickup_at
FROM src;

CREATE OR REPLACE VIEW stg.trips AS
SELECT
    CASE hvfhs_license_num
        WHEN 'HV0003' THEN 'Uber'
        WHEN 'HV0005' THEN 'Lyft'
        ELSE 'Other'
    END AS platform,
    pickup_datetime,
    CAST(pickup_datetime AS DATE) AS pickup_date,
    EXTRACT(hour FROM pickup_datetime)::INTEGER AS pickup_hour,
    CAST(date_trunc('week', CAST(pickup_datetime AS DATE)) AS DATE) AS week_start,
    EXTRACT(isodow FROM pickup_datetime)::INTEGER AS iso_dow,
    EXTRACT(isodow FROM pickup_datetime) >= 6 AS is_weekend,
    EXTRACT(hour FROM pickup_datetime)::INTEGER >= 22
        OR EXTRACT(hour FROM pickup_datetime)::INTEGER < 5 AS is_night,
    CASE
        WHEN EXTRACT(hour FROM pickup_datetime) BETWEEN 0 AND 5 THEN 'overnight'
        WHEN EXTRACT(hour FROM pickup_datetime) BETWEEN 6 AND 9 THEN 'morning'
        WHEN EXTRACT(hour FROM pickup_datetime) BETWEEN 10 AND 15 THEN 'midday'
        WHEN EXTRACT(hour FROM pickup_datetime) BETWEEN 16 AND 19 THEN 'evening'
        ELSE 'night'
    END AS time_of_day,
    CAST(PULocationID AS INTEGER) AS pu_location_id,
    CAST(DOLocationID AS INTEGER) AS do_location_id,
    CAST(trip_miles AS DOUBLE) AS trip_miles,
    CAST(trip_time AS BIGINT) AS trip_time_seconds,
    CAST(base_passenger_fare AS DOUBLE) AS passenger_fare,
    CAST(COALESCE(tolls, 0) AS DOUBLE) AS tolls,
    CAST(COALESCE(tips, 0) AS DOUBLE) AS tips,
    CAST(driver_pay AS DOUBLE) AS driver_pay,
    CAST(COALESCE(airport_fee, 0) AS DOUBLE) AS airport_fee,
    UPPER(TRIM(CAST(shared_request_flag AS VARCHAR))) AS shared_request_flag,
    UPPER(TRIM(CAST(shared_match_flag AS VARCHAR))) AS shared_match_flag,
    DATE_DIFF('second', request_datetime, pickup_datetime) AS wait_seconds
FROM raw.trips
WHERE hvfhs_license_num IN ('HV0003', 'HV0005')
  AND date_trunc('month', pickup_datetime) = DATE '__MONTH_START__'
  AND pickup_datetime IS NOT NULL
  AND dropoff_datetime IS NOT NULL
  AND pickup_datetime < dropoff_datetime
  AND CAST(PULocationID AS INTEGER) BETWEEN __MIN_LOC__ AND __MAX_LOC__
  AND CAST(DOLocationID AS INTEGER) BETWEEN __MIN_LOC__ AND __MAX_LOC__
  AND trip_miles > 0
  AND trip_miles <= __MAX_MILES__
  AND trip_time > 0
  AND trip_time <= __MAX_TRIP_SECONDS__
  AND base_passenger_fare > 0
  AND base_passenger_fare <= __MAX_FARE__
  AND driver_pay >= 0
  AND (
        request_datetime IS NULL
        OR (
            DATE_DIFF('second', request_datetime, pickup_datetime) BETWEEN 0 AND __MAX_WAIT__
        )
      );
