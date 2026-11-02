"""Add the two advanced PBIR pages without replacing the original pages.

Requires the advanced measures in the supplied semantic model. This script
changes report definitions only; semantic model changes use Power BI MCP/TOM.
"""
from pathlib import Path
import json
from build_dashboard import BASE, object_id, write_json, literal, color, obj, projection, field


def build(project):
    pages = project/'dashboard'/'TaxiAnalytics.Report'/'definition'/'pages'
    for slug, title in [('demand','Nhịp nhu cầu'), ('economics','Hiệu quả khu vực')]:
        visuals = []
        def add(name, kind, x,y,w,h, title=None, roles=None, objects=None):
            vid=object_id(slug+'_'+name)
            visual={'visualType':kind, 'drillFilterOtherVisuals':False,
                'visualContainerObjects':{
                    'background':obj(show=literal(True),color=color('#FFFFFF'),transparency=literal(0)),
                    'border':obj(show=literal(False)),
                    'padding':obj(top=literal(10),bottom=literal(10),left=literal(12),right=literal(12)),
                    'title':obj(show=literal(bool(title)),text=literal(title or ''),fontSize=literal(12),fontColor=color('#142B45')),
                    'visualHeader':obj(show=literal(False))}}
            if roles:
                visual['query']={'queryState':{r:{'projections':p} for r,p in roles.items()}}
            if objects:
                visual['objects']=objects
            item={'$schema':BASE+'item/report/definition/visualContainer/1.0.0/schema.json',
                  'name':vid,'position':{'x':x,'y':y,'z':len(visuals)*1000,'width':w,'height':h,'tabOrder':len(visuals)*1000},'visual':visual}
            visuals.append(item)
            return item
        def text(name,value,x,y,w,h,size=14):
            v=add(name,'textbox',x,y,w,h,objects={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':value,'textStyle':{'fontFamily':'Segoe UI','fontSize':f'{size}px','color':'#142B45'}}]}]}}]})
            v['visual']['visualContainerObjects']['background']=obj(show=literal(False))
            v['visual']['visualContainerObjects']['padding']=obj(top=literal(0),bottom=literal(0),left=literal(0),right=literal(0))
        def card(name,table,measure,x,full=False):
            props={'fontSize':literal(27),'color':color('#142B45')}
            if full:
                props.update(labelDisplayUnits=literal(1),labelPrecision=literal(0))
            return add(name,'card',x,120,294,104,roles={'Values':[projection(table,measure,True)]},objects={
                'labels':obj(**props),'categoryLabels':obj(show=literal(True),fontSize=literal(11),color=color('#53667D'))})
        def chart(name,kind,table,category,mt,measure,x,y,w,h,title,descending=False):
            v=add(name,kind,x,y,w,h,title,{'Category':[projection(table,category)],'Y':[projection(mt,measure,True)]},{
                'dataPoint':obj(defaultColor=color('#137F8B')),
                'categoryAxis':obj(showAxisTitle=literal(False),fontSize=literal(10),labelColor=color('#53667D')),
                'valueAxis':obj(showAxisTitle=literal(False),fontSize=literal(10),labelColor=color('#53667D')),
                'legend':obj(show=literal(False))})
            v['visual']['query']['sortDefinition']={'sort':[{'field':field(mt,measure,True) if descending else field(table,category),'direction':'Descending' if descending else 'Ascending'}],'isDefaultSort':True}
        text('heading','NYC TAXI  /  '+title.upper(),24,18,940,36,27)
        text('subtitle','Yellow Taxi • Q1/2025 • Phân tích các chuyến được ETL chấp nhận',24,61,950,26)
        add('month','slicer',1020,16,236,80,roles={'Values':[projection('Months','source_month')]},objects={
            'data':obj(mode=literal('Dropdown')),'header':obj(show=literal(True),text=literal('Tháng dữ liệu')),
            'selection':obj(selectAllCheckboxEnabled=literal(True),singleSelect=literal(False))})
        if slug=='demand':
            for name,measure,x,full in [('daily','Chuyến / ngày theo thời điểm',24,True),('days','Số ngày cùng thứ',334,True),('weekend','Tỷ trọng chuyến cuối tuần',644,False),('ticket','Tiền / chuyến theo giờ',954,False)]:
                card(name,'Hourly',measure,x,full)
            chart('weekday','clusteredColumnChart','Hourly','Thứ','Hourly','Chuyến / ngày theo thời điểm',24,244,596,250,'Nhu cầu theo thứ · chuyến bình quân / ngày')
            chart('hour','lineChart','Hourly','pickup_hour','Hourly','Chuyến / ngày theo thời điểm',640,244,616,250,'Nhịp trong ngày · chuyến / giờ / ngày')
            add('matrix','pivotTable',24,514,1232,270,'Thứ × giờ đón · chuyến / giờ / ngày cùng thứ',{
                'Rows':[projection('Hourly','Thứ')],'Columns':[projection('Hourly','pickup_hour')],
                'Values':[projection('Hourly','Chuyến / ngày theo thời điểm',True)]},
                {'rowHeaders':obj(fontSize=literal(10)),'columnHeaders':obj(fontSize=literal(10)),'values':obj(fontSize=literal(10)),
                 'subTotals':obj(rowSubtotals=literal(False),columnSubtotals=literal(False))})
            text('scope','Giờ NYC (0–23). Bình quân theo số ngày có dữ liệu cùng thứ. Tỷ trọng cuối tuần luôn theo tháng chọn. Bấm thứ/giờ để lọc.',24,806,1232,42,13)
        else:
            card('trips','Pickup','Chuyến theo khu vực',24,True)
            card('zones','Pickup','Số khu vực có chuyến',334,True)
            card('ticket_card','Pickup','Tiền / chuyến khu vực',644)
            card('flags','Pickup','Tỷ lệ gắn cờ khu vực',954)
            chart('money','clusteredBarChart','Zones','borough','Pickup','Tiền theo khu vực',24,244,596,250,'Tiền ghi nhận theo Borough · USD',True)
            chart('ticket','clusteredColumnChart','Zones','borough','Pickup','Tiền / chuyến khu vực',640,244,616,250,'Tiền / chuyến theo Borough · USD')
            v=add('detail','tableEx',24,514,1232,270,'So sánh vùng đón · bấm Borough để lọc, cuộn để xem các vùng',{'Values':[
                projection('Zones','zone'),projection('Zones','borough'),projection('Pickup','Chuyến theo khu vực',True),
                projection('Pickup','Tỷ trọng chuyến khu vực',True),projection('Pickup','Tiền theo khu vực',True),
                projection('Pickup','Tiền / chuyến khu vực',True),projection('Pickup','Tỷ lệ gắn cờ khu vực',True)]},
                {'columnHeaders':obj(fontSize=literal(10)),'values':obj(fontSize=literal(10))})
            v['visual']['query']['sortDefinition']={'sort':[{'field':field('Pickup','Chuyến theo khu vực',True),'direction':'Descending'}],'isDefaultSort':True}
            text('scope','Tiền ghi nhận không phải lợi nhuận; gồm số âm và ngoại lệ. Tỷ trọng tính trên phạm vi đang chọn. Gắn cờ ≠ gian lận.',24,806,1232,42,13)
        # All facts on each advanced page share a grain, so chart selections filter
        # the related evidence and cards. The original pages remain untouched.
        interactions=[]
        for source in visuals:
            if source['visual']['visualType'] in {'clusteredColumnChart','clusteredBarChart','lineChart'}:
                for target in visuals:
                    if target!=source and target['visual']['visualType'] not in {'textbox','slicer'}:
                        interactions.append({'source':source['name'],'target':target['name'],'type':'DataFilter'})
        assert len({v['name'] for v in visuals})==len(visuals), 'Duplicate visual identifiers'
        pid=object_id(slug)
        write_json(pages/pid/'page.json',{'$schema':BASE+'item/report/definition/page/1.0.0/schema.json','name':pid,'displayName':title,
            'displayOption':'FitToPage','height':864,'width':1280,
            'objects':{'background':obj(color=color('#F1F5F9'),transparency=literal(0))},'visualInteractions':interactions})
        for value in visuals:
            write_json(pages/pid/'visuals'/value['name']/'visual.json',value)
    meta=json.loads((pages/'pages.json').read_text(encoding='utf-8'))
    for slug in ['demand','economics']:
        if object_id(slug) not in meta['pageOrder']:
            meta['pageOrder'].append(object_id(slug))
    write_json(pages/'pages.json',meta)


if __name__=='__main__':
    build(Path(__file__).resolve().parent.parent)
