"""Cloud updater. Never invent scores when data provider fails."""
import json, traceback
from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import akshare as ak

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'
OUT.mkdir(exist_ok=True)
def dated(df):
    for name in ('日期','date','trade_date'):
        if name in df:
            a=df.copy();a['date']=pd.to_datetime(a[name],errors='coerce');return a
    raise ValueError('日期字段不存在: '+repr(list(df.columns)))
def pick(df, exact, parts):
    if exact in df:return exact
    for col in df:
        if all(p in str(col) for p in parts) and not any(x in str(col) for x in ['等权','中位数']):
            return col
    raise ValueError('找不到估值字段: '+repr(list(df.columns)))
def pct(s,value):
    a=pd.to_numeric(s,errors='coerce').dropna()
    if len(a)<100:raise ValueError('历史数据不足')
    return float((a<=value).mean()*100)
def index_data():
    a=dated(ak.stock_index_pe_lg(symbol='中证500'))
    b=dated(ak.stock_index_pb_lg(symbol='中证500'))
    ac=pick(a,'滚动市盈率',['滚动','市盈率'])
    bc=pick(b,'市净率',['市净率'])
    a=a[['date',ac]].rename(columns={ac:'pe'})
    b=b[['date',bc]].rename(columns={bc:'pb'})
    result=a.merge(b,on='date')
    for c in ('pe','pb'):result[c]=pd.to_numeric(result[c],errors='coerce')
    return result.dropna().query('pe>0 and pb>0')
def yields(start,end):
    chunks=[]
    s=start
    while s<=end:
        e=min(s+timedelta(days=330),end)
        a=dated(ak.bond_china_yield(start_date=s.strftime('%Y%m%d'),end_date=e.strftime('%Y%m%d')))
        if '曲线名称' in a:
            a=a[a['曲线名称'].astype(str).str.contains('中债国债收益率曲线',regex=False,na=False)]
        for col in ('1年','10年','30年'):
            if col not in a:raise ValueError('中债缺少 '+col)
        a=a[['date','1年','10年','30年']].rename(columns={'1年':'y1','10年':'y10','30年':'y30'})
        chunks.append(a);s=e+timedelta(days=1)
    a=pd.concat(chunks,ignore_index=True)
    for c in ('y1','y10','y30'):a[c]=pd.to_numeric(a[c],errors='coerce')
    return a.dropna().drop_duplicates('date',keep='last')
def calculate():
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    d=index_data()
    d=d[d.date>=pd.Timestamp(today-timedelta(days=12*366))]
    y=yields(today-timedelta(days=12*366),today)
    m=d.merge(y,on='date').sort_values('date').drop_duplicates('date',keep='last').set_index('date')
    if len(m)<500:raise ValueError('历史有效数据不足')
    m['erp']=100/m.pe-m.y10
    m['spread10']=m.y10-m.y1
    m['spread30']=m.y30-m.y10
    m['dev10']=m.y10-m.y10.rolling(252,min_periods=120).mean()
    m['dev30']=m.y30-m.y30.rolling(252,min_periods=120).mean()
    last=m.iloc[-1];window=m[m.index>=m.index[-1]-pd.DateOffset(years=10)]
    if len(window)<400:raise ValueError('10年分位样本太少')
    p=lambda col:pct(window[col],float(last[col]))
    scores={
      'csi500':round(.5*p('erp')+.3*(100-p('pe'))+.2*(100-p('pb'))),
      'bond10':round(.6*p('y10')+.25*p('dev10')+.15*p('spread10')),
      'bond30':round(.6*p('y30')+.25*p('spread30')+.15*p('dev30'))}
    names={'csi500':'中证500','bond10':'10年国债ETF','bond30':'30年国债ETF'}
    details={
      'csi500':[['股债风险溢价',f"{last.erp:.2f}%"],['PE-TTM',f"{last.pe:.2f}倍"],['PB',f"{last.pb:.2f}倍"],['ERP十年历史分位',f"{p('erp'):.1f}%"]],
      'bond10':[['10年国债收益率',f"{last.y10:.3f}%"],['收益率10年分位',f"{p('y10'):.1f}%"],['10Y-1Y期限利差',f"{last.spread10:.3f}%"],['相对1年收益率均值',f"{last.dev10:+.3f}%"]],
      'bond30':[['30年国债收益率',f"{last.y30:.3f}%"],['收益率10年分位',f"{p('y30'):.1f}%"],['30Y-10Y期限利差',f"{last.spread30:.3f}%"],['相对1年收益率均值',f"{last.dev30:+.3f}%"]]}
    return {'mode':'live','dataDate':str(m.index[-1].date()),'generatedAt':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'assets':[{'id':k,'name':names[k],'score':v,'metrics':details[k]} for k,v in scores.items()],'model':'10年历史分位；估值比较不代表收益预测'}
def main():
    status={'attemptAt':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
    try:
        obj=calculate()
        (OUT/'latest.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
        status.update(success=True,dataDate=obj['dataDate'])
        print('Updated',obj['dataDate'],[(a['id'],a['score']) for a in obj['assets']])
    except Exception as e:
        traceback.print_exc()
        status.update(success=False,error=str(e))
        print('Keeping last verified data')
    (OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
