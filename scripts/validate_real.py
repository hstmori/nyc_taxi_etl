"""Integration validation on actual local files, including forced replacement of every month."""
import argparse
import json
import math
import logging
from datetime import datetime, timezone
from pathlib import Path

from taxi_etl.pipeline import connect, export, load_month


def fingerprint(con):
    return {table: con.execute(f'SELECT count(*), bit_xor(hash({table})) FROM {table}').fetchone()
            for table in ['trips', 'quarantine', 'dq_missing', 'dq_checks', 'dim_zone']}


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--database', type=Path, default=Path('artifacts/taxi.duckdb'))
    args = parser.parse_args()
    con = connect(args.database)
    try:
        files = sorted(args.raw_dir.glob('yellow_tripdata_????-??.parquet'))
        assert files, 'No sources found'
        lookup = args.raw_dir / 'taxi_zone_lookup.csv'
        before = fingerprint(con)
        skipped = [load_month(con, p, lookup) for p in files]
        assert all(r['status'] == 'skipped' for r in skipped), 'Run ETL once before validation'
        replaced = [load_month(con, p, lookup, force=True) for p in files]
        after = fingerprint(con)
        assert before == after, 'Forced rerun changed stored content'
        months = con.execute('SELECT source_month,raw_rows,accepted_rows,quarantined_rows FROM etl_manifest ORDER BY source_month').fetchall()
        for month, raw, accepted, rejected in months:
            assert raw == accepted + rejected
            assert con.execute('SELECT count(*) FROM trips WHERE source_month=?', [month]).fetchone()[0] == accepted
            assert con.execute('SELECT count(*) FROM quarantine WHERE source_month=?', [month]).fetchone()[0] == rejected
        export(con, 'artifacts/exports')
        mart_count, mart_amount = con.execute('SELECT sum(trip_count),sum(recorded_total_amount) FROM mart_daily').fetchone()
        fact_count, fact_amount = con.execute('SELECT count(*),sum(total_amount) FROM trips').fetchone()
        assert mart_count == fact_count
        assert math.isclose(mart_amount, fact_amount, rel_tol=1e-10, abs_tol=.05)
        for view in ['mart_pickup_zone', 'mart_hourly']:
            assert con.execute(f'SELECT sum(trip_count) FROM {view}').fetchone()[0] == fact_count
        result = dict(validated_at_utc=datetime.now(timezone.utc).isoformat(), months=months,
                      raw_rows=sum(r[1] for r in months), accepted_rows=fact_count,
                      quarantined_rows=sum(r[3] for r in months), fingerprints_before=before,
                      fingerprints_after=after, unchanged_rerun=skipped,
                      forced_rerun=replaced, mart_trip_reconciliation='passed',
                      mart_amount_reconciliation='passed',
                      accepted_negative_amount_rows=con.execute('SELECT count(*) FROM trips WHERE total_amount<0').fetchone()[0])
        evidence = Path('docs/evidence')
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / 'integration.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        for table in ['etl_manifest', 'dq_missing', 'dq_checks', 'dim_zone']:
            target = str(evidence / f'{table}.csv').replace("'", "''")
            con.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO '{target}' (HEADER)")
        rows = '\n'.join(f'| {m} | {r:,} | {a:,} | {q:,} |' for m, r, a, q in months)
        report = f'''# Validation — local Q1/2025

Generated at {result['validated_at_utc']} (UTC).

| Month | Raw | Accepted | Quarantine |
|---|---:|---:|---:|
{rows}
| Total | {result['raw_rows']:,} | {fact_count:,} | {result['quarantined_rows']:,} |

Checks passed on the actual input files:

- Raw = accepted + quarantine, per month and overall.
- Unchanged rerun skipped all source months based on content hashes.
- Forced replacement of all source months kept row counts and row-content fingerprints identical for trips, quarantine, DQ tables and zone lookup.
- All three marts reconcile trip counts to accepted fact records.
- Daily mart amount reconciles to fact with floating-point tolerance (absolute 0.05 USD or relative 1e-10).
- Negative amounts are retained by policy; they are not assumed to be invalid transactions.

Full machine-readable results and source checksums: [integration.json](evidence/integration.json).
Per-column missing counts and percentages: [dq_missing.csv](evidence/dq_missing.csv).
Raw quality rule counts: [dq_checks.csv](evidence/dq_checks.csv).

This is a local integration run, not a production SLA or evidence of remote CI execution. Rule counts overlap; quarantine totals are distinct rows. Content fingerprints provide a rerun regression check, not proof of source truth. Unit-test results are stored in evidence/pytest.xml.
'''
        Path('docs/VALIDATION.md').write_text(report, encoding='utf-8')
        print(json.dumps({k:result[k] for k in ['raw_rows','accepted_rows','quarantined_rows','mart_trip_reconciliation','mart_amount_reconciliation']}, indent=2))
    finally:
        con.close()


if __name__ == '__main__':
    main()
