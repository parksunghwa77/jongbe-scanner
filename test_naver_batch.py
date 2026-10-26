"""Read-only NAVER OHLCV batch feasibility test; does NOT modify scanner or site.
Uses a limited representative sample to avoid placing thousands of requests on NAVER.
"""
import json, time, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import FinanceDataReader as fdr

# Mixed KOSPI/KOSDAQ sample; verify code/name mapping against listing when available.
CODES = ['005930','000660','035420','005380','000270','068270','105560','055550','012330','066570',
         '028260','003550','032830','096770','017670','034730','015760','009150','018260','010130',
         '247540','086520','196170','263750','041510','035900','091990','293490','122870','058470',
         '060310','066970','065450','078600','039030','067160','441270','064400','024740','060370']
now = datetime.now(ZoneInfo('Asia/Seoul'))
start = (now - timedelta(days=14)).date().isoformat()
end = (now + timedelta(days=1)).date().isoformat()
print('NAVER batch test / sample size:', len(CODES), 'KST:', now.isoformat(), flush=True)
results=[]
for i, code in enumerate(CODES, 1):
    entry={'code':code}
    try:
        df=fdr.DataReader('NAVER:'+code,start,end)
        if df.empty: raise ValueError('empty')
        df=df.sort_index()
        if not {'Open','High','Low','Close','Volume'}.issubset(df.columns): raise ValueError('missing OHLCV columns')
        row=df.iloc[-1]
        day=df.index[-1].date()
        valid=bool(row['Low']>0 and row['Low']<=row['Open']<=row['High'] and row['Low']<=row['Close']<=row['High'] and row['Volume']>=0)
        entry.update(date=day.isoformat(),close=int(row['Close']),valid_ohlcv=valid,calendar_lag=(now.date()-day).days)
        if not valid: entry['error']='invalid OHLCV'
    except Exception as exc:
        entry['error']=type(exc).__name__+': '+str(exc)[:150]
    results.append(entry)
    print(f'{i:02d}/{len(CODES)} '+json.dumps(entry,ensure_ascii=False),flush=True)
    time.sleep(0.6)
valid=[r for r in results if 'error' not in r]
newest=max((r['date'] for r in valid),default='none')
matching=sum(r['date']==newest for r in valid)
summary={'requested':len(CODES),'valid':len(valid),'errors':len(CODES)-len(valid),'newest_date':newest,'matching_newest':matching,'same_date_ratio':round(matching/len(valid),3) if valid else 0}
print('SUMMARY '+json.dumps(summary,ensure_ascii=False),flush=True)
print('CAUTION: This is only a sample. It does not establish full-market capacity, exchange-verified accuracy, or production suitability.',flush=True)
if len(valid)<int(len(CODES)*0.9) or (valid and matching/len(valid)<0.9):
    raise SystemExit('TEST INCONCLUSIVE: many requests failed or latest dates disagree')
