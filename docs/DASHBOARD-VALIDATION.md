# Dashboard validation

Initial two pages validated locally on 2026-11-01; expanded to four pages on 2026-11-02 with Power BI Desktop 2.142.1277.0 (2025).

## Advanced pages — 2026-11-02

- Added Nhịp nhu cầu and Hiệu quả khu vực, preserving the original two pages.
- Model now has 27 measures and the calculated weekday label Hourly[Thứ], sorted by iso_weekday. Existing 8 tables and 7 relationships retained.
- Live-engine DAX reconciled against ETL CSVs: 504 month × weekday × hour cells, 24 month × Borough aggregates, weighted amount/trip and flagged rates.
- Multi-select scenario (January + March, Saturday, 18:00) checks the trip numerator and corresponding weekday-day denominator. Weekend share deliberately retains the selected-month baseline.
- Zone shares checked for 66 Manhattan zones in January and 260 zone/Borough groups overall. ALLSELECTED removes table-row context while retaining external Borough and month selections; shares sum to 100% within scope.
- Desktop rendered both advanced pages. Weekday click tested on Saturday (13 days, 140,547 trips/day rounded); Borough click tested on Queens (963,369 trips, 69 active location IDs, USD 61.02/trip rounded). Both reset to All.
- Advanced-page month slicer tested on January: 3,473,153 accepted trips, USD 25.61/trip rounded. Reset to All.
- Static checks: 46 visual bindings, no layout overlap/out-of-canvas containers, all CSV month totals reconcile. All 59 project JSON/PBIP/PBIR/PBISM files passed schema validation after native save (zero errors).
- Evidence: dashboard-advanced-dax.json, dashboard-zone-share-dax.json, dashboard-advanced-validation.json; scripts/validate_advanced_dashboard.py reproduces the CSV comparison against the saved engine outputs.
- Demand uses observed pickup counts, not unmet demand; geography uses pickup zones. Money retains signed/flagged records and does not measure profit.

## Passed

- Opened PBIP and refreshed CSV import model in Desktop.
- Both pages rendered built-in visuals with actual Q1/2025 data.
- Live DAX: each month's Daily, Pickup and Hourly accepted trip totals match; raw = accepted + quarantine.
- Overall: 11,168,445 accepted trips; USD 286,692,371.01 recorded amount (rounded); 11,198,026 raw; 29,581 quarantine.
- Quality-page month slicer tested on January 2025: quarantine 2,073, missing 15.54% in affected columns, matching ETL. Default restored to All.
- Checks/missing grand totals return BLANK; verified in live DAX to avoid summing overlapping rule counts or across-column percentages.
- Full number formatting selected for trip count and raw/accepted/quarantine cards.
- Static check: 24 bindings, 8 tables, 7 relationships; no overlapping/out-of-canvas visual containers. CSV totals reconcile by month.
- All 35 final project JSON/PBIP/PBIR/PBISM files validated against Microsoft schemas after native Desktop save (zero errors). Schema validity alone did not guarantee rendering; both pages were also inspected in Desktop.

## Compatibility

Desktop 2025 required PBIR preview and a restart. Visual schema 2.1.0 was not resolved by this Desktop. Visual schema 1.0.0 with report document version 2.0.0 opened and rendered successfully. Report document version 4.0.0 opened the model but did not render pages in this Desktop; it is not delivered.

## Limits

Local Desktop only: no Service publication, scheduled refresh, mobile layout or RLS testing. Compact Zone labels may be shortened; use hover/scroll. Month slicers are page-scoped. Amounts retain signed and flagged records under the ETL policy.
