"""Generate a Power BI project (PBIR report + intermediate BIM for TOM/TMDL export).

The generated report uses only built-in Power BI visuals. Source CSVs remain the
ETL outputs. Run with --project-dir to place the dashboard next to that project.
"""
import argparse
import csv
import json
import hashlib
from pathlib import Path

BASE = 'https://developer.microsoft.com/json-schemas/fabric/'

def object_id(name):
    return hashlib.sha1(name.encode('utf-8')).hexdigest()[:20]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def literal(value):
    if isinstance(value, bool):
        text = str(value).lower()
    elif isinstance(value, (int, float)):
        text = f'{value}D'
    else:
        text = "'" + value.replace("'", "''") + "'"
    return {'expr': {'Literal': {'Value': text}}}


def color(value):
    return {'solid': {'color': literal(value)}}


def obj(**kwargs):
    return [{'properties': kwargs}]


def field(table, prop, measure=False):
    return {('Measure' if measure else 'Column'): {'Expression': {'SourceRef': {'Entity': table}}, 'Property': prop}}


def projection(table, prop, measure=False):
    return {'field': field(table, prop, measure), 'queryRef': f'{table}.{prop}', 'nativeQueryRef': prop}


def model(data_dir):
    specs = {
        'Daily': ('mart_daily.csv', [('source_month','string'),('pickup_date','dateTime'),('trip_count','int64'),('recorded_total_amount','double'),('avg_recorded_amount','double'),('median_distance_miles','double'),('median_duration_minutes','double'),('flagged_trip_count','int64')]),
        'Pickup': ('mart_pickup_zone.csv', [('source_month','string'),('location_id','int64'),('trip_count','int64'),('recorded_total_amount','double'),('flagged_trip_count','int64')]),
        'Hourly': ('mart_hourly.csv', [('source_month','string'),('iso_weekday','int64'),('pickup_hour','int64'),('trip_count','int64'),('recorded_total_amount','double')]),
        'Zones': ('dim_zone.csv', [('location_id','int64'),('borough','string'),('zone','string'),('service_zone','string')]),
        'LoadAudit': ('etl_manifest.csv', [('source_month','string'),('raw_rows','int64'),('accepted_rows','int64'),('quarantined_rows','int64')]),
        'Missing': ('dq_missing.csv', [('source_month','string'),('column_name','string'),('raw_rows','int64'),('missing_count','int64'),('missing_pct','double')]),
        'Checks': ('dq_checks.csv', [('source_month','string'),('check_name','string'),('row_count','int64')]),
        'Months': ('etl_manifest.csv', [('source_month','string')]),
    }
    mtype = {'string':'type text', 'int64':'Int64.Type','double':'type number','dateTime':'type date'}
    tables = []
    for name, (filename, columns) in specs.items():
        selected = ', '.join('"' + c + '"' for c,_ in columns)
        types = ', '.join('{"' + c + '", ' + mtype[t] + '}' for c,t in columns)
        expression = f'''let
    Source = Csv.Document(File.Contents(DataRoot & "\\{filename}"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Selected = Table.SelectColumns(Headers, {{{selected}}}),
    Typed = Table.TransformColumnTypes(Selected, {{{types}}}, "en-US")
in
    Typed'''
        if name == 'Zones':
            expression = expression.replace('in\n    Typed', '    , Labeled = Table.ReplaceValue(Typed, "", "Unknown", Replacer.ReplaceValue, {"borough", "zone", "service_zone"})\nin\n    Labeled')
        table = {'name':name,'columns':[{'name':c,'dataType':t,'sourceColumn':c,'summarizeBy':'none'} for c,t in columns],
                 'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':expression}}]}
        tables.append(table)
    measures = {
        'Daily': [('Số chuyến','SUM(Daily[trip_count])','#,0'),
                  ('Tổng tiền ghi nhận','SUM(Daily[recorded_total_amount])','$#,0.00;($#,0.00)'),
                  ('Tiền / chuyến','DIVIDE([Tổng tiền ghi nhận],[Số chuyến])','$0.00'),
                  ('Chuyến gắn cờ','SUM(Daily[flagged_trip_count])','#,0'),
                  ('Tỷ lệ gắn cờ','DIVIDE([Chuyến gắn cờ],[Số chuyến])','0.0%')],
        'Pickup': [('Chuyến theo khu vực','SUM(Pickup[trip_count])','#,0'),
                   ('Hạng khu vực','RANKX(ALL(Zones[zone]),[Chuyến theo khu vực],,DESC,Dense)','0')],
        'Hourly': [('Chuyến theo giờ','SUM(Hourly[trip_count])','#,0')],
        'LoadAudit': [('Dòng nguồn','SUM(LoadAudit[raw_rows])','#,0'),
                      ('Dòng chấp nhận','SUM(LoadAudit[accepted_rows])','#,0'),
                      ('Dòng cách ly','SUM(LoadAudit[quarantined_rows])','#,0'),
                      ('Tỷ lệ cách ly','DIVIDE([Dòng cách ly],[Dòng nguồn])','0.00%'),
                      ('Tỷ lệ chấp nhận','DIVIDE([Dòng chấp nhận],[Dòng nguồn])','0.00%')],
        'Missing': [('Giá trị thiếu','IF(ISINSCOPE(Missing[column_name]), SUM(Missing[missing_count]))','#,0'),
                    ('Tỷ lệ thiếu','IF(ISINSCOPE(Missing[column_name]), DIVIDE(SUM(Missing[missing_count]),SUM(Missing[raw_rows])))','0.00%')],
        'Checks': [('Số dòng theo kiểm tra','IF(ISINSCOPE(Checks[check_name]), SUM(Checks[row_count]))','#,0')],
    }
    for table in tables:
        table['measures'] = [{'name':n,'expression':e,'formatString':f,'displayFolder':'Dashboard'} for n,e,f in measures.get(table['name'],[])]
        for col in table['columns']:
            col['isHidden'] = col['name'] not in {'source_month','pickup_date','borough','zone','pickup_hour','column_name','check_name'}
            if table['name']=='Daily' and col['name']=='pickup_date':
                col['formatString']='dd MMM'
        table['description'] = f'ETL export: {specs[table["name"]][0]}. Grain and caveats: docs/power-bi.md.'
    relationships = [{'name':f'Months_{name}','fromTable':name,'fromColumn':'source_month','toTable':'Months','toColumn':'source_month','crossFilteringBehavior':'oneDirection'} for name in ['Daily','Pickup','Hourly','LoadAudit','Missing','Checks']]
    relationships.append({'name':'Zones_Pickup','fromTable':'Pickup','fromColumn':'location_id','toTable':'Zones','toColumn':'location_id','crossFilteringBehavior':'oneDirection'})
    return {'name':'TaxiAnalytics','compatibilityLevel':1600,'model':{
        'culture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3','sourceQueryCulture':'en-US',
        'dataAccessOptions':{'legacyRedirects':True,'returnErrorValuesAsNull':True},
        'annotations':[{'name':'PBI_QueryOrder','value':json.dumps(list(specs))},{'name':'__PBI_TimeIntelligenceEnabled','value':'0'}],
        'expressions':[{'name':'DataRoot','kind':'m','expression':'"'+str(data_dir).replace('"','""')+'" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
        'tables':tables,'relationships':relationships}}


def build_report(root):
    report = root / 'TaxiAnalytics.Report'
    definition = report / 'definition'
    write_json(root / 'TaxiAnalytics.pbip', {'$schema':BASE+'pbip/pbipProperties/1.0.0/schema.json','version':'1.0','artifacts':[{'report':{'path':'TaxiAnalytics.Report'}}],'settings':{'enableAutoRecovery':True}})
    write_json(report/'definition.pbir', {'$schema':BASE+'item/report/definitionProperties/1.0.0/schema.json','version':'4.0','datasetReference':{'byPath':{'path':'../TaxiAnalytics.SemanticModel'}}})
    write_json(root/'TaxiAnalytics.SemanticModel'/'definition.pbism',{'$schema':BASE+'item/semanticModel/definitionProperties/1.0.0/schema.json','version':'4.0','settings':{}})
    write_json(definition/'version.json',{'$schema':BASE+'item/report/definition/versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    write_json(definition/'report.json',{'$schema':BASE+'item/report/definition/report/1.0.0/schema.json',
        'themeCollection':{'baseTheme':{'name':'CY24SU06','reportVersionAtImport':'5.55','type':'SharedResources'}},
        'layoutOptimization':'None','settings':{'useStylableVisualContainerHeader':True,'exportDataMode':'AllowSummarized','defaultDrillFilterOtherVisuals':True}})
    pages = [('overview','Tổng quan'),('quality','Chất lượng dữ liệu')]
    write_json(definition/'pages'/'pages.json',{'$schema':BASE+'item/report/definition/pagesMetadata/1.0.0/schema.json','pageOrder':[object_id(x[0]) for x in pages],'activePageName':object_id('overview')})
    for page_slug, display in pages:
        page_id=object_id(page_slug)
        page_dir = definition/'pages'/page_id
        visuals = []

        def add(name, kind, x,y,w,h, title=None, roles=None, objects=None):
            name=object_id(page_slug+'_'+name)
            vco={'background':obj(show=literal(True),color=color('#FFFFFF'),transparency=literal(0)),
                 'border':obj(show=literal(False)),
                 'padding':obj(top=literal(10),bottom=literal(10),left=literal(12),right=literal(12)),
                 'title':obj(show=literal(bool(title)),text=literal(title or ''),fontSize=literal(12),fontColor=color('#142B45')),
                 'visualHeader':obj(show=literal(False))}
            visual={'visualType':kind,'visualContainerObjects':vco,'drillFilterOtherVisuals':False}
            if roles:
                visual['query']={'queryState':{role:{'projections':items} for role,items in roles.items()}}
            if objects:
                visual['objects']=objects
            item={'$schema':BASE+'item/report/definition/visualContainer/1.0.0/schema.json','name':name,
                  'position':{'x':x,'y':y,'z':len(visuals)*1000,'width':w,'height':h,'tabOrder':len(visuals)*1000},'visual':visual}
            visuals.append(item)
            return item

        def textbox(name,text,x,y,w,h,size=16,foreground='#142B45',fill=False):
            item=add(name,'textbox',x,y,w,h,objects={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':text,'textStyle':{'fontFamily':'Segoe UI','fontSize':f'{size}px','color':foreground}}]}]}}]})
            item['visual']['visualContainerObjects']['background']=obj(show=literal(fill),color=color('#142B45'))
            item['visual']['visualContainerObjects']['padding']=obj(top=literal(0),bottom=literal(0),left=literal(0),right=literal(0))

        def card(name,table,measure,x,w):
            item=add(name,'card',x,120,w,104,roles={'Values':[projection(table,measure,True)]},objects={
                'labels':obj(fontSize=literal(27),color=color('#142B45')),
                'categoryLabels':obj(show=literal(True),fontSize=literal(11),color=color('#53667D'))})
            if measure=='Số chuyến' or measure.startswith('Dòng '):
                item['visual']['objects']['labels'][0]['properties'].update(labelDisplayUnits=literal(1),labelPrecision=literal(0))

        def chart(name,kind,table,column,measure_table,measure,x,y,w,h,title,series=None,sort_desc=False):
            roles={'Category':[projection(table,column)],'Y':[projection(measure_table,measure,True)]}
            if series:
                roles['Series']=[projection(*series)]
            item=add(name,kind,x,y,w,h,title,roles,{
                'dataPoint':obj(defaultColor=color('#137F8B')),
                'categoryAxis':obj(showAxisTitle=literal(False),fontSize=literal(10),labelColor=color('#53667D')),
                'valueAxis':obj(showAxisTitle=literal(False),fontSize=literal(10),labelColor=color('#53667D'),start=literal(0)),
                'labels':obj(show=literal(kind=='clusteredBarChart'),fontSize=literal(10)),
                'legend':obj(show=literal(bool(series)))})
            item['visual']['query']['sortDefinition']={'sort':[{'field':field(measure_table,measure,True) if sort_desc else field(table,column),'direction':'Descending' if sort_desc else 'Ascending'}],'isDefaultSort':True}
            return item

        textbox('heading','NYC TAXI  /  '+display.upper(),24,18,920,36,27)
        textbox('subtitle','Yellow Taxi • Q1/2025 • Chọn tháng để xem cùng phạm vi dữ liệu',24,61,920,26,14,'#53667D')
        add('month_filter','slicer',1020,16,236,80,roles={'Values':[projection('Months','source_month')]},objects={
            'data':obj(mode=literal('Dropdown')),'header':obj(show=literal(True),text=literal('Tháng dữ liệu')),
            'selection':obj(selectAllCheckboxEnabled=literal(True),singleSelect=literal(False))})
        if page_slug=='overview':
            for args in [('trip_card','Daily','Số chuyến',24,294),('amount_card','Daily','Tổng tiền ghi nhận',334,302),('avg_card','Daily','Tiền / chuyến',652,294),('flag_card','Daily','Tỷ lệ gắn cờ',962,294)]:
                card(*args)
            chart('daily_trips','lineChart','Daily','pickup_date','Daily','Số chuyến',24,244,756,260,'Số chuyến theo ngày')
            chart('borough_trips','clusteredBarChart','Zones','borough','Pickup','Chuyến theo khu vực',800,244,456,260,'Khu vực đón khách · Borough',sort_desc=True)
            chart('hour_trips','clusteredColumnChart','Hourly','pickup_hour','Hourly','Chuyến theo giờ',24,524,756,260,'Số chuyến theo giờ đón · tổng trong kỳ')
            chart('zone_table','clusteredBarChart','Zones','zone','Pickup','Chuyến theo khu vực',800,524,456,260,'Khu vực đón khách · cuộn để xem thêm',sort_desc=True)
            textbox('scope','Chỉ gồm dòng được chấp nhận. Chuyến gắn cờ vẫn được tính; số tiền giữ dấu âm và ngoại lệ, đơn vị USD.',24,808,1232,38,13,'#53667D')
        else:
            for args in [('raw_card','LoadAudit','Dòng nguồn',24,294),('accepted_card','LoadAudit','Dòng chấp nhận',334,302),('reject_card','LoadAudit','Dòng cách ly',652,294),('rate_card','LoadAudit','Tỷ lệ cách ly',962,294)]:
                card(*args)
            chart('monthly_rejects','clusteredColumnChart','Months','source_month','LoadAudit','Dòng cách ly',24,244,548,260,'Dòng cách ly theo tháng')
            chart('missing_rates','clusteredBarChart','Missing','column_name','Missing','Tỷ lệ thiếu',592,244,664,260,'Tỷ lệ thiếu theo cột · trên dữ liệu nguồn',sort_desc=True)
            add('checks_table','tableEx',24,524,548,260,'Kiểm tra chất lượng · trên dữ liệu nguồn',{'Values':[projection('Checks','check_name'),projection('Checks','Số dòng theo kiểm tra',True)]}, {'columnHeaders':obj(fontSize=literal(11)),'values':obj(fontSize=literal(11))})
            add('missing_table','tableEx',592,524,664,260,'Chi tiết missing · số lượng và tỷ lệ',{'Values':[projection('Missing','column_name'),projection('Missing','Giá trị thiếu',True),projection('Missing','Tỷ lệ thiếu',True)]}, {'columnHeaders':obj(fontSize=literal(11)),'values':obj(fontSize=literal(11))})
            textbox('scope','Các kiểm tra có thể chồng lấp, không cộng thành số dòng lỗi. Missing tính trên raw; 0 không đồng nghĩa null.',24,808,1232,38,13,'#53667D')
        interactions=[]
        for source in visuals:
            if source['visual']['visualType'] not in {'slicer','textbox','card'}:
                for target in visuals:
                    if source!=target:
                        interactions.append({'source':source['name'],'target':target['name'],'type':'NoFilter'})
        write_json(page_dir/'page.json',{'$schema':BASE+'item/report/definition/page/1.0.0/schema.json','name':page_id,'displayName':display,
            'displayOption':'FitToPage','height':864,'width':1280,'objects':{'background':obj(color=color('#F1F5F9'),transparency=literal(0))},'visualInteractions':interactions})
        for visual in visuals:
            write_json(page_dir/'visuals'/visual['name']/'visual.json',visual)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--overwrite',action='store_true',help='Replace generated definitions; may reset Desktop edits')
    args=parser.parse_args()
    project=args.project_dir.resolve()
    data=(args.data_dir or project/'artifacts'/'exports').resolve()
    # Header and input completeness check before generating anything.
    assert all((data/f).exists() for f in ['mart_daily.csv','mart_pickup_zone.csv','mart_hourly.csv','dim_zone.csv','etl_manifest.csv','dq_missing.csv','dq_checks.csv'])
    dashboard=project/'dashboard'
    if dashboard.exists() and not args.overwrite:
        raise FileExistsError('Dashboard already exists. Refresh in Power BI; use --overwrite only to regenerate intentionally.')
    write_json(dashboard/'model.bim',model(data))
    build_report(dashboard)
    print(dashboard)


if __name__=='__main__':
    main()
