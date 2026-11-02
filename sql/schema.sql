CREATE TABLE IF NOT EXISTS dim_zone (
    location_id INTEGER PRIMARY KEY, borough VARCHAR, zone VARCHAR, service_zone VARCHAR
);
CREATE TABLE IF NOT EXISTS trips (
    source_month VARCHAR, source_row_number BIGINT,
    vendorid INTEGER, tpep_pickup_datetime TIMESTAMP, tpep_dropoff_datetime TIMESTAMP,
    passenger_count DOUBLE, trip_distance DOUBLE, ratecodeid DOUBLE,
    store_and_fwd_flag VARCHAR, pulocationid INTEGER, dolocationid INTEGER,
    payment_type BIGINT, fare_amount DOUBLE, extra DOUBLE, mta_tax DOUBLE,
    tip_amount DOUBLE, tolls_amount DOUBLE, improvement_surcharge DOUBLE,
    total_amount DOUBLE, congestion_surcharge DOUBLE, airport_fee DOUBLE,
    cbd_congestion_fee DOUBLE, quality_flags VARCHAR, duration_minutes DOUBLE,
    PRIMARY KEY (source_month, source_row_number)
);
CREATE TABLE IF NOT EXISTS quarantine AS SELECT *, ''::VARCHAR AS reject_reason FROM trips WHERE false;
CREATE TABLE IF NOT EXISTS etl_manifest (
    source_month VARCHAR PRIMARY KEY, source_sha256 VARCHAR, lookup_sha256 VARCHAR,
    policy_version VARCHAR, raw_rows BIGINT, accepted_rows BIGINT,
    quarantined_rows BIGINT, source_filename VARCHAR, loaded_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS dq_missing (
    source_month VARCHAR, column_name VARCHAR, raw_rows BIGINT, missing_count BIGINT, missing_pct DOUBLE
);
CREATE TABLE IF NOT EXISTS dq_checks (source_month VARCHAR, check_name VARCHAR, row_count BIGINT);
