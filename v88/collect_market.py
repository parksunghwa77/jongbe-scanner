#!/usr/bin/env python3
"""Build an auditable pre-open market snapshot for Jongbe v8.8.

No orders, no credentials embedded, no invented fills. Four-factor forecast uses only
records observed BEFORE the target Korean 09:00 open. Yahoo daily bars are proxies,
NOT live futures tick data. KOSPI 200 night market needs a verified provider or a
manually timestamped CSV; missing data remain missing, never silently set to 0.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote

import requests

KST = ZoneInfo('Asia/Seoul')
NY = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
FIELDS = ('nq_pct', 'kospi_night_pct', 'us10y_bp', 'sox_pct')
MAX_HISTORY = 340


def good_num(x, limit=30):
    try:
        value = float(x)
        return value if math.isfinite(value) and abs(value) <= limit else None
    except (ValueError, TypeError):
        return None


def next_target(now):
    import exchange_calendars as ec
    cal = ec.get_calendar('XKRX')
    day = now.date()
    # This program is run either before opening or after the prior close.
    if now.time() >= time(9):
        day += timedelta(days=1)
    for _ in range(15):
        if cal.is_session(day.isoformat()):
            return day
        day += timedelta(days=1)
    raise RuntimeError('KRX 거래일 계산 실패')


def fetch_yahoo_daily(session, symbol, now):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + quote(symbol, safe='')
    resp = session.get(url, params={'range':'10d', 'interval':'1d','events':'false'}, timeout=16)
    resp.raise_for_status()
    chart = resp.json().get('chart', {})
    if chart.get('error'):
        raise RuntimeError('Yahoo chart API error')
    items = chart.get('result') or []
    if not items:
        raise RuntimeError('Yahoo chart data empty')
    d = items[0]
    times = d.get('timestamp') or []
    closes = ((d.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
    pairs_by_day = {}
    ny_now = now.astimezone(NY)
    for stamp, val in zip(times, closes):
        val = good_num(val, 1e9)
        if val is None or val <= 0:
            continue
        source_date = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(NY).date()
        # An unfinished futures daily candle (e.g. Sunday Globex opening)
        # must never be treated as the final daily close.
        if source_date.weekday() >= 5: continue
        if source_date > ny_now.date(): continue
        if source_date == ny_now.date() and ny_now.time() < time(17, 30): continue
        pairs_by_day[source_date] = val
    pairs = sorted(pairs_by_day.items())
    if len(pairs) < 2:
        raise RuntimeError('Yahoo: fewer than 2 valid daily closes')
    (d0, older), (d1, newer) = pairs[-2:]
    if d1 < now.astimezone(NY).date()-timedelta(days=5):
        raise RuntimeError('Yahoo: last observation too old')
    return {'value': round((newer/older-1)*100, 4), 'observation_date': d1.isoformat(),
            'previous_date': d0.isoformat(), 'source':f'Yahoo Chart daily {symbol}',
            'method':'confirmed-ish daily close change, delayed/unofficial; NOT live overnight price'}


def fetch_fred_daily(session, now):
    resp = session.get('https://fred.stlouisfed.org/graph/fredgraph.csv', params={'id':'DGS10'}, timeout=18)
    resp.raise_for_status()
    records = list(csv.DictReader(io.StringIO(resp.text)))
    pairs=[]
    for r in records:
        raw=r.get('DGS10'); val=good_num(raw,30)
        when=r.get('observation_date') or r.get('DATE') or r.get('date')
        if val is not None and when and len(when)==10 and when <= now.date().isoformat():
            pairs.append((when,val))
    if len(pairs)<2:raise RuntimeError('FRED: fewer than 2 valid yields')
    (old_date,old),(new_date,new)=pairs[-2:]
    if date.fromisoformat(new_date) < now.date()-timedelta(days=7):
        raise RuntimeError('FRED: 10y yield observation is too old')
    return {'value':round((new-old)*100,3),'observation_date':new_date,'previous_date':old_date,
            'source':'FRED DGS10 (Federal Reserve H.15)',
            'method':'difference between last two published daily yields, basis points; release can lag'}


def read_night_csv(path, target, now):
    if not path.exists(): return None
    # KRX night session starts 18:00 on the preceding calendar day and ends 06:00.
    # There is no Sunday-night KOSPI200 session for Monday's cash open.
    from exchange_calendars import get_calendar
    previous=target-timedelta(days=1)
    if not get_calendar('XKRX').is_session(previous.isoformat()):return None
    session_start=datetime.combine(previous,time(18),KST)
    # For next-day open research, use only completed night-session observations.
    night_finish=datetime.combine(target,time(6),KST)
    entries=[]
    with path.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        if r.get('target_session')!=target.isoformat():continue
        pct=good_num(r.get('change_pct'))
        try:
            observed=datetime.fromisoformat(r['observed_at_kst'])
            if observed.tzinfo is None: continue
            observed=observed.astimezone(KST)
        except (ValueError, TypeError, KeyError):
            continue
        cutoff=datetime.combine(target,time(9),KST)
        if pct is None or observed>now or observed>=cutoff or observed<night_finish or observed<session_start:continue
        # A manual update must explicitly indicate its own source/observation time.
        if not r.get('source','').strip():continue
        entries.append((observed,pct,r['source'].strip()[:120]))
    if not entries:return None
    stamp,pct,source=max(entries,key=lambda r:r[0])
    return {'value':pct,'observation_date':stamp.date().isoformat(),
            'observed_at_kst':stamp.isoformat(timespec='seconds'),
            'source':'user-entered '+source, 'method':'post-06:00 night-futures observation; independently verify settlement and source'}


def get_verified_provider(session,target,now):
    url=os.environ.get('V88_MARKET_PROVIDER_URL','').strip()
    if not url:return {}
    headers={}
    token=os.environ.get('V88_MARKET_PROVIDER_TOKEN','').strip()
    if token:headers['Authorization']='Bearer '+token
    resp=session.get(url,headers=headers,timeout=18)
    resp.raise_for_status()
    item=resp.json()
    if not isinstance(item,dict) or item.get('target_session')!=target.isoformat():
        raise RuntimeError('provider target_session mismatch')
    stamp=datetime.fromisoformat(str(item.get('observed_at_kst','')))
    if stamp.tzinfo is None:raise RuntimeError('provider timezone missing')
    stamp=stamp.astimezone(KST)
    if stamp>now or stamp>=datetime.combine(target,time(9),KST) or stamp<datetime.combine(target,time(6),KST):
        raise RuntimeError('provider timestamp after target open')
    source=str(item.get('source','')).strip()
    if not source: raise RuntimeError('provider source missing')
    result={}
    for field in FIELDS:
        val=good_num((item.get('factors') or {}).get(field),150 if field=='us10y_bp' else 30)
        if val is not None:
            result[field]={'value':val,'source':source[:120],'method':'configured market-data provider',
                           'observed_at_kst':stamp.isoformat(timespec='seconds')}
    return result


def load_history(path):
    if not path.exists():return []
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        if obj.get('schema')=='jongbe-market-history-v1' and isinstance(obj.get('sessions'),list):
            return [r for r in obj['sessions'] if isinstance(r,dict)]
    except (OSError,ValueError,TypeError):pass
    return []


def generate(now=None, session=None, folder=ROOT):
    now=now or datetime.now(KST)
    if now.tzinfo is None: raise ValueError('timezone aware now required')
    now=now.astimezone(KST)
    target=next_target(now)
    before=now.date()==target and now.time()<time(9)
    # The published EOD file must correspond exactly to the previous KRX trading
    # session, not merely be 'older than' the next target session.
    from exchange_calendars import get_calendar
    previous_session=get_calendar('XKRX').previous_session(target.isoformat()).date().isoformat()
    if not before:
        # The 09:30/18:15 legacy EOD scans should not replace the 08:10
        # pre-open market snapshot with a future target of incomplete data.
        print('v8.8 pre-open collection skipped after 09:00 KST; keeping cached snapshot.')
        existing=folder/'market-latest.json'
        return json.loads(existing.read_text(encoding='utf-8')) if existing.exists() else None
    session=session or requests.Session()
    session.headers.update({'User-Agent':'JongbeResearch/8.8 (daily-data diagnostic)', 'Accept':'application/json,text/csv'})
    sources={};errors={}
    for name,fn in [('nq_pct',lambda:fetch_yahoo_daily(session,'NQ=F',now)),
                    ('sox_pct',lambda:fetch_yahoo_daily(session,'^SOX',now)),
                    ('us10y_bp',lambda:fetch_fred_daily(session,now))]:
        try:sources[name]=fn()
        except (Exception) as exc:
            errors[name]=f'{type(exc).__name__}: source unavailable' # no URLs, keys, or sensitive responses
    night=read_night_csv(folder/'kospi200-night.csv',target,now)
    if night:sources['kospi_night_pct']=night
    try:
        # Licensed/approved provider values, when supplied, override public proxies.
        sources.update(get_verified_provider(session,target,now))
    except Exception as exc:
        errors['provider']=f'{type(exc).__name__}: configured source unavailable'
    values={}
    for k in FIELDS:
        if k in sources:
            numeric=good_num(sources[k].get('value'),150 if k=='us10y_bp' else 30)
            if numeric is not None: values[k]=numeric
    status={k:('ok' if k in values else 'missing') for k in FIELDS}
    complete=all(k in values for k in FIELDS) and before
    data={'schema':'jongbe-market-snapshot-v1', 'session_date':target.isoformat(),
          'previous_session':previous_session,
          'generated_at_kst':now.isoformat(timespec='seconds'),
          'collected_before_open':bool(before),'complete':bool(complete),
          'factors':values,'status':status,'sources':sources,
          'warnings':['Yahoo 일봉은 NQ 실시간 야간변동을 직접 나타내지 않으며 10년물 FRED는 발표 시차가 있습니다.',
                      '코스피200 야간선물의 검증 가능한 데이터가 없으면 임의로 0을 입력하지 않습니다.',
                      '기준일·관측 시각을 확인하세요. 투자 추천이나 자동 주문이 아닙니다.'],
          'errors':errors}
    folder.mkdir(parents=True,exist_ok=True)
    # Never publish credentials, full raw API responses, or personal account info.
    (folder/'market-latest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    path=folder/'market-history.json'
    history=load_history(path)
    if complete:
        history=[r for r in history if r.get('session_date')!=target.isoformat()]
        history.append({k:data[k] for k in ('session_date','generated_at_kst','collected_before_open','complete','factors')})
    history.sort(key=lambda r:r.get('session_date',''))
    history=history[-MAX_HISTORY:]
    path.write_text(json.dumps({'schema':'jongbe-market-history-v1','sessions':history},ensure_ascii=False,indent=2),encoding='utf-8')
    print('v8.8 market snapshot:', target.isoformat(), 'complete=',complete,
          'fields=',','.join(k for k in FIELDS if k in values),'history=',len(history))
    return data


if __name__=='__main__':
    generate()
