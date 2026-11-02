"""Check local dashboard bindings, layout bounds and ETL-export reconciliation."""
import csv
import json
import math
from pathlib import Path


def main():
    project=Path(__file__).resolve().parent.parent
    root=project/'dashboard'
    model=json.loads((root/'model.bim').read_text(encoding='utf-8'))['model']
    tables={t['name']:t for t in model['tables']}
    checked=0
    for page in (root/'TaxiAnalytics.Report'/'definition'/'pages').glob('*/page.json'):
        info=json.loads(page.read_text(encoding='utf-8'))
        boxes=[]
        for path in page.parent.glob('visuals/*/visual.json'):
            value=json.loads(path.read_text(encoding='utf-8'))
            p=value['position']
            assert p['x']>=0 and p['y']>=0
            assert p['x']+p['width']<=info['width'] and p['y']+p['height']<=info['height'], path
            for role in value['visual'].get('query',{}).get('queryState',{}).values():
                for projection in role['projections']:
                    field=projection['field']
                    kind=next(iter(field))
                    entity=field[kind]['Expression']['SourceRef']['Entity']
                    prop=field[kind]['Property']
                    assert entity in tables
                    keys='measures' if kind=='Measure' else 'columns'
                    assert prop in {x['name'] for x in tables[entity][keys]}, (path,entity,prop)
            boxes.append((value['name'],p))
            checked+=1
        for i,(name,a) in enumerate(boxes):
            for other,b in boxes[i+1:]:
                overlap=(a['x']<b['x']+b['width'] and b['x']<a['x']+a['width'] and a['y']<b['y']+b['height'] and b['y']<a['y']+a['height'])
                assert not overlap,(name,other)
    exports=project/'artifacts'/'exports'
    def read(name):
        with (exports/name).open(encoding='utf-8',newline='') as f:
            return list(csv.DictReader(f))
    daily=read('mart_daily.csv')
    manifest=read('etl_manifest.csv')
    trips=sum(int(r['trip_count']) for r in daily)
    assert trips==sum(int(r['accepted_rows']) for r in manifest)
    months={r['source_month'] for r in manifest}
    for filename in ['mart_pickup_zone.csv','mart_hourly.csv']:
        rows=read(filename)
        assert sum(int(r['trip_count']) for r in rows)==trips
        for month in months:
            assert sum(int(r['trip_count']) for r in rows if r['source_month']==month)==sum(int(r['trip_count']) for r in daily if r['source_month']==month)
    zones=read('dim_zone.csv')
    ids=[r['location_id'] for r in zones]
    assert len(ids)==len(set(ids))
    assert {r['location_id'] for r in read('mart_pickup_zone.csv')}<=set(ids)
    result={'visual_bindings_checked':checked,'model_tables':len(tables),'model_relationships':len(model['relationships']),
            'layout_bounds_and_overlap':'passed','csv_month_reconciliation':'passed','accepted_trips':trips,
            'recorded_amount_usd':sum(float(r['recorded_total_amount']) for r in daily),
            'note':'Static/data checks only; Desktop render and live DAX checks are recorded separately.'}
    evidence=project/'docs'/'evidence'/'dashboard-static.json'
    evidence.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
