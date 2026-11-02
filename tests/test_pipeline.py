import pandas as pd
import pytest

from taxi_etl.pipeline import connect, export, load_month


@pytest.fixture
def dataset(tmp_path):
    row = dict(VendorID=1, tpep_pickup_datetime=pd.Timestamp('2025-01-15 10:00'),
               tpep_dropoff_datetime=pd.Timestamp('2025-01-15 10:15'),
               passenger_count=1., trip_distance=2., RatecodeID=1., store_and_fwd_flag='N',
               PULocationID=1, DOLocationID=2, payment_type=1, fare_amount=10., extra=0.,
               mta_tax=.5, tip_amount=2., tolls_amount=0., improvement_surcharge=1.,
               total_amount=13.5, congestion_surcharge=0., Airport_fee=0., cbd_congestion_fee=0.)
    rows = [row.copy() for _ in range(7)]
    rows[1]['total_amount'] = -13.5
    rows[2]['passenger_count'] = None
    rows[3]['tpep_dropoff_datetime'] = pd.Timestamp('2025-01-15 09:59')
    rows[4]['tpep_pickup_datetime'] = pd.Timestamp('2024-12-31')
    rows[5]['PULocationID'] = 999
    # Row 6 intentionally equals row 0: no unsupported business deduplication.
    path = tmp_path / 'yellow_tripdata_2025-01.parquet'
    pd.DataFrame(rows).to_parquet(path, index=False)
    lookup = tmp_path / 'taxi_zone_lookup.csv'
    pd.DataFrame({'LocationID': [1, 2], 'Borough': ['A', 'B'], 'Zone': ['X', 'Y'],
                  'service_zone': ['Yellow', None]}).to_csv(lookup, index=False)
    con = connect(tmp_path / 'test.duckdb')
    yield con, path, lookup, tmp_path
    con.close()


def test_reconcile_quarantine_and_keep_soft_flags(dataset):
    con, path, lookup, _ = dataset
    result = load_month(con, path, lookup)
    assert (result['raw_rows'], result['accepted_rows'], result['quarantined_rows']) == (7, 4, 3)
    assert con.execute('SELECT count(*) FROM trips WHERE total_amount<0').fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM trips WHERE contains(quality_flags,'missing_passenger_count')").fetchone()[0] == 1
    assert con.execute("SELECT missing_count FROM dq_missing WHERE column_name='passenger_count'").fetchone()[0] == 1


def test_skip_and_forced_rerun_are_idempotent(dataset):
    con, path, lookup, _ = dataset
    load_month(con, path, lookup)
    before = con.execute('SELECT bit_xor(hash(trips)) FROM trips').fetchone()[0]
    assert load_month(con, path, lookup)['status'] == 'skipped'
    load_month(con, path, lookup, force=True)
    after = con.execute('SELECT bit_xor(hash(trips)) FROM trips').fetchone()[0]
    assert before == after
    assert con.execute('SELECT count(*) FROM trips').fetchone()[0] == 4
    assert con.execute('SELECT count(*) FROM etl_manifest').fetchone()[0] == 1
    assert con.execute('SELECT count(*) FROM dq_missing').fetchone()[0] == 20


def test_changed_file_replaces_partition(dataset):
    con, path, lookup, _ = dataset
    load_month(con, path, lookup)
    frame = pd.read_parquet(path)
    frame.loc[0, 'total_amount'] = 99.
    frame.to_parquet(path, index=False)
    assert load_month(con, path, lookup)['status'] == 'loaded'
    assert con.execute('SELECT total_amount FROM trips WHERE source_row_number=0').fetchone()[0] == 99.
    assert con.execute('SELECT count(*) FROM trips').fetchone()[0] == 4


def test_schema_failure_preserves_committed_partition(dataset):
    con, path, lookup, _ = dataset
    load_month(con, path, lookup)
    old_hash = con.execute('SELECT source_sha256 FROM etl_manifest').fetchone()[0]
    pd.read_parquet(path).drop(columns='fare_amount').to_parquet(path, index=False)
    with pytest.raises(ValueError, match='Schema drift'):
        load_month(con, path, lookup)
    assert con.execute('SELECT count(*) FROM trips').fetchone()[0] == 4
    assert con.execute('SELECT source_sha256 FROM etl_manifest').fetchone()[0] == old_hash


def test_duplicate_lookup_rejected(dataset):
    con, path, lookup, _ = dataset
    frame = pd.read_csv(lookup)
    pd.concat([frame, frame.iloc[:1]]).to_csv(lookup, index=False)
    with pytest.raises(ValueError, match='unique'):
        load_month(con, path, lookup)
    assert con.execute('SELECT count(*) FROM trips').fetchone()[0] == 0


def test_exports_reconcile_to_fact(dataset):
    con, path, lookup, tmp_path = dataset
    load_month(con, path, lookup)
    export(con, tmp_path / 'exports')
    mart = pd.read_csv(tmp_path / 'exports/mart_daily.csv')
    assert mart.trip_count.sum() == 4
    assert mart.recorded_total_amount.sum() == pytest.approx(27.)
    assert (tmp_path / 'exports/dq_missing.csv').exists()


def test_replacing_one_month_preserves_other_month(dataset):
    con, path, lookup, tmp_path = dataset
    load_month(con, path, lookup)
    frame = pd.read_parquet(path)
    for col in ['tpep_pickup_datetime', 'tpep_dropoff_datetime']:
        frame[col] = frame[col] + pd.DateOffset(months=1)
    february = tmp_path / 'yellow_tripdata_2025-02.parquet'
    frame.to_parquet(february, index=False)
    load_month(con, february, lookup)
    before = con.execute("SELECT count(*),bit_xor(hash(trips)) FROM trips WHERE source_month='2025-02'").fetchone()
    load_month(con, path, lookup, force=True)
    after = con.execute("SELECT count(*),bit_xor(hash(trips)) FROM trips WHERE source_month='2025-02'").fetchone()
    assert before == after
    assert con.execute('SELECT count(*) FROM etl_manifest').fetchone()[0] == 2
