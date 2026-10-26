"""Read-only diagnostic: investigate 145210 and compare NAVER with marcap on overlapping dates.
Run in the existing test-naver.yml job; does not change deployed scanner data.
"""
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import pandas as pd
import requests
import FinanceDataReader as fdr

now = datetime.now(ZoneInfo('Asia/Seoul'))
start = (now - timedelta(days=30)).date().isoformat()
end = (now + timedelta(days=1)).date().isoformat()
watch = {'145210':'데이터 오류 점검', '005930':'삼성전자', '000660':'SK하이닉스', '441270':'파인엠텍'}
cols = ['Open','High','Low','Close','Volume']

url = f'https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{now.year}.parquet'
try:
    res = requests.get(url, timeout=(10,60))
    res.raise_for_status()
    cap = pd.read_parquet(BytesIO(res.content))
    cap['Code'] = cap['Code'].astype(str).str.zfill(6)
    cap['Date'] = pd.to_datetime(cap['Date']).dt.normalize()
    print('MARCAP latest:',cap.Date.max().date(),flush=True)
except Exception as exc:
    cap = None
    print('MARCAP unavailable:',repr(exc),flush=True)

for code,name in watch.items():
    print('\n===',code,name,'===',flush=True)
    try:
        df = fdr.DataReader('NAVER:'+code, start, end).sort_index()
        if df.empty: raise ValueError('empty NAVER data')
        df.index = pd.to_datetime(df.index).normalize()
        print('NAVER recent OHLCV:', df[cols].tail(5).to_json(orient='index',date_format='iso',force_ascii=False),flush=True)
        errors=[]
        for when,row in df.tail(10).iterrows():
            o,h,l,c,v=[pd.to_numeric(row.get(k),errors='coerce') for k in cols]
            if not (all(pd.notna(x) for x in [o,h,l,c,v]) and l>0 and l<=o<=h and l<=c<=h and v>=0):
                errors.append({'date':when.date().isoformat(),'o':str(o),'h':str(h),'l':str(l),'c':str(c),'v':str(v)})
        print('NAVER invalid recent bars:',json.dumps(errors,ensure_ascii=False),flush=True)
        if cap is not None:
            mc = cap[cap.Code==code].set_index('Date').sort_index()
            shared = df.index.intersection(mc.index)
            print('Overlap dates:',len(shared),flush=True)
            comparisons=[]
            for day in shared[-5:]:
                a,b=df.loc[day],mc.loc[day]
                mismatches={col:{'naver':str(a[col]),'marcap':str(b[col])} for col in cols if pd.notna(a[col]) and pd.notna(b[col]) and float(a[col])!=float(b[col])}
                comparisons.append({'date':day.date().isoformat(),'mismatch':mismatches})
            print('MARCAP comparisons:',json.dumps(comparisons,ensure_ascii=False),flush=True)
    except Exception as exc:
        print('ERROR',code,type(exc).__name__,str(exc)[:300],flush=True)
print('\nDIAGNOSTIC COMPLETE: provider mismatch or adjusted price differences require human review before using live.',flush=True)
