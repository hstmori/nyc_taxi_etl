# Validation — local Q1/2025

Generated at 2026-11-01T07:33:05.612971+00:00 (UTC).

| Month | Raw | Accepted | Quarantine |
|---|---:|---:|---:|
| 2025-01 | 3,475,226 | 3,473,153 | 2,073 |
| 2025-02 | 3,577,543 | 3,572,348 | 5,195 |
| 2025-03 | 4,145,257 | 4,122,944 | 22,313 |
| Total | 11,198,026 | 11,168,445 | 29,581 |

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
