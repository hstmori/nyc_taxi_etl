"""File-partition ETL: content hashes, atomic replacement, quarantine and SQL marts."""
import argparse
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

LOG = logging.getLogger(__name__)
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
POLICY_VERSION = "1"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def connect(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='2GB'")
    con.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    return con


def load_month(con, parquet, lookup, force=False):
    parquet, lookup = Path(parquet), Path(lookup)
    match = re.fullmatch(r"yellow_tripdata_(\d{4}-\d{2})\.parquet", parquet.name)
    if not match:
        raise ValueError(f"Unexpected filename: {parquet.name}")
    month = match.group(1)
    datetime.strptime(month, "%Y-%m")
    started = time.perf_counter()
    source_hash, zone_hash = sha256(parquet), sha256(lookup)
    previous = con.execute("SELECT source_sha256, lookup_sha256, policy_version FROM etl_manifest WHERE source_month=?", [month]).fetchone()
    if previous == (source_hash, zone_hash, POLICY_VERSION) and not force:
        LOG.info("SKIP %s: content and policy unchanged", month)
        return {"month": month, "status": "skipped"}
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("CREATE OR REPLACE TEMP TABLE zones_in AS SELECT * FROM read_csv_auto(?, header=true)", [str(lookup)])
        bad_keys = con.execute("SELECT count(*)-count(DISTINCT LocationID) FROM zones_in").fetchone()[0]
        if bad_keys or con.execute("SELECT count(*) FROM zones_in").fetchone()[0] == 0:
            raise ValueError("Zone lookup must have non-null unique LocationID keys and at least one row")
        con.execute("CREATE OR REPLACE TEMP TABLE staged AS SELECT *, file_row_number AS source_row_number FROM read_parquet(?, file_row_number=true)", [str(parquet)])
        columns = con.execute("DESCRIBE staged").fetchall()
        # Normalize column spelling while preserving physical source order.
        source_columns = [row[0] for row in columns if row[0] not in ("file_row_number", "source_row_number")]
        normalized = [name.lower() for name in source_columns]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Column names collide after normalization")
        expected = {r[0] for r in con.execute("DESCRIBE trips").fetchall()} - {"source_month", "source_row_number", "quality_flags", "duration_minutes"}
        if set(normalized) != expected:
            raise ValueError(f"Schema drift: missing={expected-set(normalized)}, extra={set(normalized)-expected}")
        select = ", ".join('"' + c.replace('"', '""') + '" AS "' + c.lower() + '"' for c in source_columns)
        con.execute(f"CREATE OR REPLACE TEMP TABLE normalized AS SELECT {select}, source_row_number FROM staged")
        month_sql = literal(month + "-01")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE assessed AS SELECT *,
            concat_ws('|',
              CASE WHEN tpep_pickup_datetime IS NULL OR tpep_dropoff_datetime IS NULL THEN 'missing_timestamp' END,
              CASE WHEN tpep_dropoff_datetime <= tpep_pickup_datetime THEN 'nonpositive_duration' END,
              CASE WHEN tpep_pickup_datetime < DATE {month_sql} OR tpep_pickup_datetime >= DATE {month_sql} + INTERVAL '1 month' THEN 'pickup_outside_source_month' END,
              CASE WHEN NOT EXISTS (SELECT 1 FROM zones_in z WHERE z.LocationID=n.PULocationID) OR NOT EXISTS (SELECT 1 FROM zones_in z WHERE z.LocationID=n.DOLocationID) THEN 'unknown_zone' END
            ) AS reject_reason,
            concat_ws('|',
              CASE WHEN total_amount < 0 THEN 'negative_total' END,
              CASE WHEN total_amount = 0 THEN 'zero_total' END,
              CASE WHEN trip_distance = 0 THEN 'zero_distance' END,
              CASE WHEN trip_distance < 0 OR trip_distance > 200 THEN 'distance_review' END,
              CASE WHEN total_amount > 1000 THEN 'amount_review' END,
              CASE WHEN passenger_count IS NULL THEN 'missing_passenger_count' END,
              CASE WHEN passenger_count = 0 THEN 'zero_passenger_count' END
            ) AS quality_flags,
            date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime)/60.0 AS duration_minutes
          FROM normalized n""")
        con.execute("DELETE FROM trips WHERE source_month=?", [month])
        con.execute("DELETE FROM quarantine WHERE source_month=?", [month])
        con.execute("DELETE FROM dq_missing WHERE source_month=?", [month])
        con.execute("DELETE FROM dq_checks WHERE source_month=?", [month])
        for target, condition in (("trips", "reject_reason=''"), ("quarantine", "reject_reason<>''")):
            exclusion = " EXCLUDE (reject_reason)" if target == "trips" else ""
            con.execute(f"INSERT INTO {target} BY NAME SELECT ? AS source_month, *{exclusion} FROM assessed WHERE {condition}", [month])
        for c in normalized:
            escaped = '"' + c + '"'
            con.execute(f"INSERT INTO dq_missing SELECT ?, ?, count(*), count(*)-count({escaped}), 100.0*(count(*)-count({escaped}))/nullif(count(*),0) FROM normalized", [month, c])
        checks = {
            "quarantined": "reject_reason<>''", "flagged": "quality_flags<>''",
            "end_before_start": "tpep_dropoff_datetime<tpep_pickup_datetime",
            "equal_times": "tpep_dropoff_datetime=tpep_pickup_datetime",
            "negative_total": "total_amount<0", "zero_distance": "trip_distance=0",
            "outside_month": "contains(reject_reason,'pickup_outside_source_month')",
        }
        for name, predicate in checks.items():
            con.execute(f"INSERT INTO dq_checks SELECT ?, ?, count(*) FILTER (WHERE {predicate}) FROM assessed", [month, name])
        raw, accepted, rejected = con.execute("SELECT count(*), count(*) FILTER(WHERE reject_reason=''), count(*) FILTER(WHERE reject_reason<>'') FROM assessed").fetchone()
        if raw != accepted + rejected:
            raise RuntimeError("Reconciliation failed")
        con.execute("DELETE FROM dim_zone")
        con.execute("INSERT INTO dim_zone SELECT LocationID, Borough, Zone, service_zone FROM zones_in")
        con.execute("DELETE FROM etl_manifest WHERE source_month=?", [month])
        con.execute("INSERT INTO etl_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)",
                    [month, source_hash, zone_hash, POLICY_VERSION, raw, accepted, rejected, parquet.name])
        con.execute("COMMIT")
        result = {"month": month, "status": "loaded", "raw_rows": raw,
                  "accepted_rows": accepted, "quarantined_rows": rejected,
                  "source_sha256": source_hash, "seconds": round(time.perf_counter()-started, 2)}
        LOG.info("LOAD %s", json.dumps(result))
        return result
    except Exception:
        con.execute("ROLLBACK")
        raise


def export(con, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    con.execute((SQL_DIR / "marts.sql").read_text(encoding="utf-8"))
    tables = ["mart_daily", "mart_pickup_zone", "mart_hourly", "dim_zone", "dq_missing", "dq_checks", "etl_manifest"]
    for table in tables:
        path = literal(destination / f"{table}.csv")
        con.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO {path} (HEADER, DELIMITER ',')")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=Path("artifacts/taxi.duckdb"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/exports"))
    parser.add_argument("--month", action="append", help="YYYY-MM; may be repeated")
    parser.add_argument("--force", action="store_true", help="Atomically replace selected partitions even if unchanged")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    log_path = args.output_dir / f"run-{run_id}.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")])
    record = {"run_id": run_id, "started_utc": datetime.now(timezone.utc).isoformat(), "status": "running", "partitions": []}
    con = None
    try:
        lookup = args.raw_dir / "taxi_zone_lookup.csv"
        if not lookup.is_file():
            raise FileNotFoundError(lookup)
        files = sorted(args.raw_dir.glob("yellow_tripdata_????-??.parquet"))
        if args.month:
            files = [args.raw_dir / f"yellow_tripdata_{m}.parquet" for m in args.month]
        if not files:
            raise ValueError("No monthly Parquet files found")
        con = connect(args.database)
        for path in files:
            record["partitions"].append(load_month(con, path, lookup, args.force))
        export(con, args.output_dir)
        record["status"] = "success"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        LOG.exception("ETL failed; active month rolled back. Earlier committed months remain available.")
        raise
    finally:
        if con:
            con.close()
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (args.output_dir / f"run-{run_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

