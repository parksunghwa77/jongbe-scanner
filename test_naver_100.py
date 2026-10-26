"""Read-only 100-stock NAVER EOD feasibility test. Does not update the live scanner.

Sample: 50 KOSPI and 50 KOSDAQ common stocks from a current public listing.
Checks response completeness, same-day coverage, error frequency and retry outcomes.
"""
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd

KST = ZoneInfo('Asia/Seoul')
now = datetime.now(KST)
start = (now - timedelta(days=14)).date().isoformat()
end = (now + timedelta(days=1)).date().isoformat()

print('100-stock NAVER EOD read-only test / KST', now.isoformat(), flush=True)
listing = fdr.StockListing('KRX')
if listing is None or listing.empty:
    raise SystemExit('STOP: Cannot get current stock listing; no fabricated ticker sample.')

listing = listing.copy()
code_col = next((c for c in ['Code', 'Symbol'] if c in listing.columns), None)
market_col = next((c for c in ['Market', 'MarketName'] if c in listing.columns), None)
if not code_col or not market_col:
    raise SystemExit('STOP: Unrecognized KRX listing columns: ' + str(list(listing.columns)))
listing['ticker'] = listing[code_col].astype(str).str.strip().str.zfill(6)
listing['market'] = listing[market_col].astype(str).str.upper().str.strip()
listing = listing[listing['ticker'].str.fullmatch(r'\d{6}') & listing['market'].isin(['KOSPI','KOSDAQ'])]
listing = listing.drop_duplicates('ticker')
if len(listing) < 100:
    raise SystemExit(f'STOP: Only {len(listing)} eligible KOSPI/KOSDAQ listings')

# Repeatable sample spread across code ranges; not a random claim of representativeness.
codes=[]
for market in ('KOSPI', 'KOSDAQ'):
    pool = sorted(listing.loc[listing.market == market, 'ticker'].tolist())
    if len(pool) < 50:
        raise SystemExit(f'STOP: Not enough {market} tickers for 50-stock sample')
    idx = [(k * (len(pool) - 1)) // 49 for k in range(50)]
    codes += [(pool[i], market) for i in idx]

results = []
for i, (code, market) in enumerate(codes, 1):
    item = {'code': code, 'market': market}
    for attempt in range(1, 4):
        try:
            df = fdr.DataReader('NAVER:' + code, start, end)
            if df is None or df.empty:
                raise ValueError('empty data')
            if not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(df.columns):
                raise ValueError('missing OHLCV columns')
            df = df.sort_index()
            row = df.iloc[-1]
            day = pd.Timestamp(df.index[-1]).date()
            vals = [pd.to_numeric(row[c], errors='coerce') for c in ('Open','High','Low','Close','Volume')]
            o,h,l,c,v = vals
            valid = bool(all(pd.notna(x) for x in vals) and l>0 and l<=o<=h and l<=c<=h and v>=0)
            if not valid:
                raise ValueError('invalid OHLCV')
            item.update(date=day.isoformat(), close=int(c), valid_ohlcv=True, attempts=attempt)
            break
        except Exception as exc:
            item['error'] = type(exc).__name__ + ': ' + str(exc)[:160]
            item['attempts'] = attempt
            if attempt < 3:
                time.sleep(2 * attempt)
    if 'date' in item:
        item.pop('error', None)
    results.append(item)
    print(f'{i:03d}/100 '+json.dumps(item,ensure_ascii=False),flush=True)
    time.sleep(0.8)  # Avoid hammering the remote provider.

valid = [r for r in results if 'date' in r]
newest = max((r['date'] for r in valid), default=None)
latest_count = sum(r['date']==newest for r in valid)
summary = {'requested':100, 'valid':len(valid), 'errors':100-len(valid),
           'newest_date':newest, 'matching_newest':latest_count,
           'same_date_ratio':round(latest_count/len(valid),3) if valid else 0,
           'retries_needed':sum(r.get('attempts',1)>1 for r in results),
           'failed': [r for r in results if 'date' not in r]}
print('SUMMARY '+json.dumps(summary,ensure_ascii=False),flush=True)
print('CAUTION: This tests response format and coverage, NOT exchange-verified price accuracy, provider permission or whole-market scalability.',flush=True)
if len(valid) < 90 or not valid or latest_count/len(valid) < 0.9:
    raise SystemExit('TEST INCONCLUSIVE: fewer than 90 valid codes or inconsistent latest dates')
print('TEST PASS: sample collection only, not approved for production substitution',flush=True)
