#!/usr/bin/env python3
"""Optional, provenance-preserving public-market enrichment for Jongbe V8.8.

Reads already produced results.json (EOD as-of) and two configured API endpoints.
No account/order/portfolio data. Fail closed: no fabricated classifications or flows.
The provider JSON is an integration contract, not a claim that a provider is
connected or that a legal classification has been independently authenticated.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
KST = ZoneInfo('Asia/Seoul')
CODE = re.compile(r'^\d{6}$')
DAY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MAX_ITEMS = 5000
MAX_AGE_DAYS = 550


def is_day(text):
    if not isinstance(text, str) or not DAY.fullmatch(text):
        return False
    try:
        return date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def num(x):
    if isinstance(x,bool) or x is None:
        return None
    try:
        n=float(x)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) and abs(n)<=100000 else None


def observed(value, day):
    try:
        d=datetime.fromisoformat(str(value)).astimezone(KST)
        if datetime.fromisoformat(str(value)).tzinfo is None:return None
    except (ValueError, TypeError):
        return None
    start=datetime.combine(date.fromisoformat(day), time(9), KST)
    end=datetime.combine(date.fromisoformat(day), time(18), KST)
    return d if start<=d<end else None


def provider(session, env_name, token_name):
    url=os.getenv(env_name,'').strip()
    if not url:
        return None
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname:
        raise ValueError('provider endpoint must be HTTPS')
    token=os.getenv(token_name,'')
    headers={'Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    response=session.get(url,headers=headers,timeout=15)
    response.raise_for_status()
    if len(response.content)>8_000_000:raise ValueError('provider payload too large')
    data=response.json()
    if not isinstance(data,dict):raise ValueError('provider must return object')
    return data


def normalized_classification(payload, asof):
    records=payload.get('entries')
    if payload.get('schema')!='jongbe-corporate-classification-v1' or not isinstance(records,dict):
        raise ValueError('unrecognized corporate classification schema')
    today=date.fromisoformat(asof)
    valid={}
    for code,entry in list(records.items())[:MAX_ITEMS]:
        if not CODE.fullmatch(str(code)) or not isinstance(entry,dict):continue
        d=entry.get('checked_on');source=str(entry.get('source','')).strip()[:160]
        kind=entry.get('category')
        if kind not in ('large','mid','sme') or not is_day(d) or len(source)<3:continue
        delta=(today-date.fromisoformat(d)).days
        if not 0<=delta<=MAX_AGE_DAYS:continue
        valid[str(code)]={'category':kind,'checked_on':d,'source':source}
    return valid


def normalized_flows(payload,asof):
    records=payload.get('entries')
    if payload.get('schema')!='jongbe-investor-flows-v1' or payload.get('session_date')!=asof or not isinstance(records,dict):
        raise ValueError('flow session date or schema mismatch')
    valid={}
    for code,entry in list(records.items())[:MAX_ITEMS]:
        if not CODE.fullmatch(str(code)) or not isinstance(entry,dict):continue
        foreign=num(entry.get('foreign_net_eok'))
        inst=num(entry.get('institution_net_eok'))
        stamp=observed(entry.get('observed_at_kst'),asof)
        source=str(entry.get('source','')).strip()[:160]
        if foreign is None or inst is None or stamp is None or len(source)<3:continue
        valid[str(code)]={'foreign_net_eok':foreign,'institution_net_eok':inst,
                          'observed_at_kst':stamp.isoformat(timespec='seconds'),'source':source}
    return valid


def save(path, schema, entries, asof=None):
    data={'schema':schema,'entries':entries}
    if asof is not None:data['session_date']=asof
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def update(root=ROOT,session=None):
    repo=root.parent
    rs=repo/'results.json'
    if not rs.exists():
        raise RuntimeError('results.json missing: EOD must be generated first')
    end=json.loads(rs.read_text(encoding='utf-8'))
    asof=end.get('asof')
    if not is_day(asof):
        raise RuntimeError('invalid EOD asof: refusing any reference data update')
    codes={str(r.get('code','')) for r in end.get('rows',[]) if isinstance(r,dict)}
    session=session or requests.Session()
    state={}
    try:
        data=provider(session,'V88_CLASS_PROVIDER_URL','V88_CLASS_PROVIDER_TOKEN')
        if data is not None:
            entries=normalized_classification(data,asof)
            # Only actual EOD-stock codes are published; avoid mass leakage.
            entries={k:v for k,v in entries.items() if k in codes}
            save(root/'corporate-classification.json','jongbe-corporate-classification-v1',entries)
            state['corporate']='updated '+str(len(entries))
        else:
            state['corporate']='not configured; existing data unchanged'
    except Exception as e:
        state['corporate']=f'unavailable ({type(e).__name__}); existing data unchanged'
    try:
        data=provider(session,'V88_FLOW_PROVIDER_URL','V88_FLOW_PROVIDER_TOKEN')
        if data is not None:
            entries=normalized_flows(data,asof)
            entries={k:v for k,v in entries.items() if k in codes}
            save(root/'investor-flows.json','jongbe-investor-flows-v1',entries,asof)
            state['flows']='updated '+str(len(entries))
        else:
            # Any flow file from prior session remains on disk but UI requires
            # exact session_date match and does NOT show it as today's flow.
            state['flows']='not configured; UI uses missing status'
    except Exception as e:
        state['flows']=f'unavailable ({type(e).__name__}); UI uses missing status'
    print('v8.8 optional references:',state)
    return state


if __name__=='__main__':update()
