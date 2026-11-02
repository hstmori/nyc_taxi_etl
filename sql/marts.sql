-- Amounts remain signed. These are recorded passenger charges, not operator profit.
-- No joins before aggregation: preserve trip grain and avoid accidental fan-out.
CREATE OR REPLACE VIEW mart_daily AS
SELECT source_month, CAST(tpep_pickup_datetime AS DATE) AS pickup_date,
       count(*) AS trip_count, sum(total_amount) AS recorded_total_amount,
       avg(total_amount) AS avg_recorded_amount, median(trip_distance) AS median_distance_miles,
       median(duration_minutes) AS median_duration_minutes,
       count(*) FILTER(WHERE quality_flags<>'') AS flagged_trip_count
FROM trips GROUP BY ALL;
CREATE OR REPLACE VIEW mart_pickup_zone AS
SELECT source_month, pulocationid AS location_id, count(*) AS trip_count,
       sum(total_amount) AS recorded_total_amount,
       count(*) FILTER(WHERE quality_flags<>'') AS flagged_trip_count
FROM trips GROUP BY ALL;
CREATE OR REPLACE VIEW mart_hourly AS
SELECT source_month, isodow(tpep_pickup_datetime) AS iso_weekday,
       hour(tpep_pickup_datetime) AS pickup_hour, count(*) AS trip_count,
       sum(total_amount) AS recorded_total_amount
FROM trips GROUP BY ALL;
