"""Reconcile saved live-engine DAX results against ETL CSV exports."""
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent.parent
    def csv_rows(name):
        with (root/'artifacts'/'exports'/name).open(encoding='utf-8',newline='') as f:
            return list(csv.DictReader(f))
    evidence=json.loads((root/'docs'/'evidence'/'dashboard-advanced-dax.json').read_text(encoding='utf-8'))
    def live(key):
        assert not evidence['queries'][key]['data']['isTruncated']
        return evidence['queries'][key]['data']['rows']
    def close(a,b):
        assert math.isclose(a,b,rel_tol=1e-10,abs_tol=0.00001),(a,b)
    daily=csv_rows('mart_daily.csv')
    hours=csv_rows('mart_hourly.csv')
    pickup=csv_rows('mart_pickup_zone.csv')
    zones={r['location_id']:r for r in csv_rows('dim_zone.csv')}
    day_counts=defaultdict(int)
    for r in daily:
        day_counts[r['source_month'],date.fromisoformat(r['pickup_date']).isoweekday()]+=1
    for r in live('monthly'):
        month=r['Months[source_month]']
        h=[x for x in hours if x['source_month']==month]
        p=[x for x in pickup if x['source_month']==month]
        trips=sum(int(x['trip_count']) for x in h)
        days=sum(n for (m,_),n in day_counts.items() if m==month)
        amount=sum(float(x['recorded_total_amount']) for x in h)
        flags=sum(int(x['flagged_trip_count']) for x in p)
        assert r['[Trips]']==r['[ZoneTrips]']==trips
        assert r['[Days]']==days
        assert r['[Flags]']==flags
        assert r['[ZoneCount]']==len({x['location_id'] for x in p if int(x['trip_count'])>0})
        close(r['[Average]'],trips/days)
        close(r['[Amount]'],amount)
        close(r['[ZoneAmount]'],amount)
        close(r['[ZoneTicket]'],amount/trips)
        close(r['[FlagRate]'],flags/trips)
        close(r['[Weekend]'],sum(int(x['trip_count']) for x in h if int(x['iso_weekday']) in (6,7))/trips)
    grid={(r['source_month'],int(r['iso_weekday']),int(r['pickup_hour'])):int(r['trip_count']) for r in hours}
    assert len(live('grid'))==len(grid)==504
    for r in live('grid'):
        m,d,h=r['Months[source_month]'],r['Hourly[iso_weekday]'],r['Hourly[pickup_hour]']
        assert r['[Trips]']==grid[m,d,h]
        assert r['[Days]']==day_counts[m,d]
        close(r['[Average]'],grid[m,d,h]/day_counts[m,d])
    for r in live('zones'):
        m,b=r['Months[source_month]'],r['Zones[borough]']
        rows=[x for x in pickup if x['source_month']==m and (zones[x['location_id']]['borough'] or 'Unknown')==b]
        trips=sum(int(x['trip_count']) for x in rows)
        amount=sum(float(x['recorded_total_amount']) for x in rows)
        flags=sum(int(x['flagged_trip_count']) for x in rows)
        assert r['[Trips]']==trips and r['[Flags]']==flags
        close(r['[Amount]'],amount)
        close(r['[Ticket]'],amount/trips)
        close(r['[FlagRate]'],flags/trips)
    selected=live('selection')[0]
    months={'2025-01','2025-03'}
    trips=sum(n for (m,d,h),n in grid.items() if m in months and d==6 and h==18)
    days=sum(n for (m,d),n in day_counts.items() if m in months and d==6)
    assert selected['[Trips]']==trips and selected['[Days]']==days
    close(selected['[Average]'],trips/days)
    all_trips=sum(n for (m,d,h),n in grid.items() if m in months)
    close(selected['[Weekend]'],sum(n for (m,d,h),n in grid.items() if m in months and d in (6,7))/all_trips)
    share_evidence=json.loads((root/'docs'/'evidence'/'dashboard-zone-share-dax.json').read_text(encoding='utf-8'))
    shares=share_evidence['queries']['shares']['data']['rows']
    close(sum(x['[Share]'] for x in shares),1)
    denominator=sum(int(x['trip_count']) for x in pickup if x['source_month']=='2025-01' and zones[x['location_id']]['borough']=='Manhattan')
    for r in shares:
        close(r['[Share]'],r['[Trips]']/denominator)
    all_shares=share_evidence['queries']['allShares']['data']['rows']
    close(sum(r['[Share]'] for r in all_shares),1)
    all_trips=sum(int(x['trip_count']) for x in pickup)
    for r in all_shares:
        close(r['[Share]'],r['[Trips]']/all_trips)
    result={'status':'passed','monthly_scenarios':len(live('monthly')),'weekday_hour_month_cells':504,
        'borough_month_scenarios':len(live('zones')),'zone_shares_checked':len(shares),
        'multi_month_weekday_hour_filter':'passed','weighted_ticket_and_flag_rates':'passed',
        'all_zone_shares_checked':len(all_shares),'source_dax_timestamp':evidence['checkedAt'],
        'share_dax_timestamp':share_evidence['checkedAt']}
    (root/'docs'/'evidence'/'dashboard-advanced-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
