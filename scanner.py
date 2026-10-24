"""종베 스캐너 v5: 거래일 지연 검증 + 과거 후보의 다음날 성과 추적.

FinanceData/marcap 공개 일봉 데이터는 당일 종가가 늦게 반영될 수 있습니다.
거래소 XKRX 거래일 캘린더 기준의 기대 기준일과 원본 최신 거래일을
비교하고 늦으면 공개 데이터의 지연 사실을 결과에 명시합니다.

KRX/pykrx 원격 조회가 21일 중 0일 성공하던 문제를 회피하기 위해,
GitHub에 공개된 연도별 한국 주식 마감 OHLCV 스냅샷을 내려받습니다.
자료가 오래됐거나 불완전하면 실패하고 기존 사이트 배포를 보존합니다.
실시간 신호/매수 추천 기능이 아닙니다.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import datetime as dt
import json
import logging
import os
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import exchange_calendars as xcals

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results.json'
KST = ZoneInfo('Asia/Seoul')
HISTORY_DAYS = 55
BACKTEST_DAYS = 15
BACKTEST_TOP_N = 10
MAX_STALE_CALENDAR_DAYS = 12
MAX_LAG_SESSIONS = 5  # 소스가 이보다 오래됐으면 배포 중지
DATA_URL = 'https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{year}.parquet'
MARKET_MIN = {'KOSPI': 400, 'KOSDAQ': 500}
log = logging.getLogger('jongbe')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def expected_trading_date(now: dt.datetime) -> dt.date:
    """마감 확정 전(16:30 KST)엔 이전 거래일, 이후엔 당일 거래일.

    주말 및 거래소 공식 휴장일은 XKRX 거래일 달력에 따라 건너뜁니다.
    """
    local = now.astimezone(KST)
    day = local.date()
    if local.time() < dt.time(16, 30):
        day -= dt.timedelta(days=1)
    calendar = xcals.get_calendar('XKRX')
    return calendar.date_to_session(pd.Timestamp(day), direction='previous').date()


def trading_day_gap(actual: dt.date, expected: dt.date) -> int:
    """실제 분석일 이후 ~ 기준 거래일까지 빠진 *거래일* 개수."""
    if actual >= expected:
        return 0
    calendar = xcals.get_calendar('XKRX')
    return len(calendar.sessions_in_range(pd.Timestamp(actual) + pd.Timedelta(days=1),
                                          pd.Timestamp(expected)))


def download_year(year: int) -> pd.DataFrame:
    url = DATA_URL.format(year=year)
    errors = []
    for attempt in range(3):
        try:
            log.info('시세 원본 다운로드 시작: %s', url)
            r = requests.get(url + f'?t={int(time.time())}', timeout=(15, 100), headers={
                'User-Agent':'jongbe-scanner/4.2 (educational github action)',
                'Cache-Control':'no-cache',
            })
            r.raise_for_status()
            if len(r.content) < 1_000_000:
                raise ValueError(f'원본이 비정상적으로 작음: {len(r.content)} bytes')
            df = pd.read_parquet(BytesIO(r.content))
            log.info('%s 데이터 로드: %,d행, %s', year, len(df), ','.join(map(str, df.columns)))
            return df
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'{year}년 일봉 다운로드/읽기 실패: {"; ".join(errors)}')


def get_data(reference: dt.date) -> pd.DataFrame:
    years = [reference.year]
    # 1~3월에는 지난해의 21거래일이 필요할 수 있음.
    if reference.month <= 3:
        years.append(reference.year - 1)
    frames = [download_year(y) for y in years]
    df = pd.concat(frames, ignore_index=True)
    columns = {'Date','Code','Name','Market','Open','High','Low','Close','Volume','Amount'}
    missing = columns - set(df.columns)
    if missing:
        raise RuntimeError(f'marcap 데이터 필수 열 누락: {sorted(missing)}')
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.tz_localize(None)
    df = df[df['Date'].notna() & (df['Date'] <= pd.Timestamp(reference))].copy()
    df['Code'] = df['Code'].astype('string').str.strip().str.zfill(6)
    df['Market'] = df['Market'].astype('string').str.upper().str.strip()
    df = df[df['Market'].isin(['KOSPI','KOSDAQ']) & df['Code'].str.fullmatch(r'\d{6}',na=False)].copy()
    if df.empty:
        raise RuntimeError('코스피/코스닥 종목 행이 0건임: marcap 데이터의 Market·Code 형식 확인 필요')
    df = df.drop_duplicates(subset=['Date', 'Code'], keep='last')
    for col in ('Open','High','Low','Close','Volume','Amount'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    latest = df['Date'].max().date()
    if (reference - latest).days > MAX_STALE_CALENDAR_DAYS:
        raise RuntimeError(f'시세 원본이 오래됨: 원본 최신 {latest}, 분석 목표일 {reference}. 이전 배포 유지.')
    dates = sorted(df['Date'].drop_duplicates().tolist(), reverse=True)
    good_dates = []
    for day in dates:
        today_df = df[df['Date'] == day]
        market_counts = today_df.groupby('Market')['Code'].count().to_dict()
        if all(market_counts.get(m, 0) >= mincount for m, mincount in MARKET_MIN.items()):
            good_dates.append(day)
        if len(good_dates) >= HISTORY_DAYS:
            break
    if len(good_dates) < HISTORY_DAYS:
        raise RuntimeError(f'전체 시장 데이터 {HISTORY_DAYS}일 필요, 정상 거래일 {len(good_dates)}일만 확보. 이전 배포 유지.')
    filtered = df[df['Date'].isin(good_dates)]
    log.info('원본 최신 %s / 채택 기준일 %s / 거래일 %s일 / 최근 종목 %s개',
             latest, max(good_dates).date(), len(good_dates),
             len(filtered[filtered['Date']==max(good_dates)]))
    return filtered


def analyze(df: pd.DataFrame, now: dt.datetime) -> dict:
    history = []
    for date, part in sorted(df.groupby('Date'), key=lambda x:x[0]):
        day = part.set_index('Code')
        # 기존 v4 점수 알고리즘이 사용하는 칼럼 이름에 맞춤.
        renamed = day[['Open','High','Low','Close','Volume','Amount','Market']].rename(columns={
            'Open':'시가','High':'고가','Low':'저가','Close':'종가',
            'Volume':'거래량','Amount':'거래대금','Market':'market'})
        renamed['name'] = day['Name'].astype(str)
        history.append((date.strftime('%Y-%m-%d'), renamed))
    if len(history) != HISTORY_DAYS:
        raise RuntimeError(f'수집된 거래일 부족: {len(history)}')
    latest_date, latest = history[-1]
    close = pd.concat([frame['종가'].rename(day) for day,frame in history],axis=1)
    volume = pd.concat([frame['거래량'].rename(day) for day,frame in history],axis=1)
    valid = (close.notna().all(axis=1)&(close>0).all(axis=1)&volume.notna().all(axis=1))
    close = close.loc[valid]
    volume = volume.loc[valid]
    latest = latest.loc[latest.index.intersection(close.index)].copy()
    latest = latest.loc[(latest['종가']>0)&(latest['거래량']>0)&(latest['거래대금']>0)&(latest['고가']>=latest['저가'])]
    close=close.loc[latest.index]
    volume=volume.loc[latest.index]
    if len(latest)<500:
        raise RuntimeError(f'21거래일 분석에 적합한 종목이 {len(latest)}개뿐임. 이전 배포 유지.')
    ma5=close.iloc[:,-5:].mean(axis=1)
    ma20=close.iloc[:,-20:].mean(axis=1)
    prev_volume=volume.iloc[:,:-1].mean(axis=1)
    ratio=(latest['거래량']/prev_volume.where(prev_volume>0)).fillna(0).clip(upper=100000)
    highlow=(latest['고가']-latest['저가']).replace(0, float('nan'))
    pos=((latest['종가']-latest['저가'])*100/highlow).fillna(50).clip(0,100)
    prev_close = close.iloc[:,-2]
    change = ((latest['종가']/prev_close - 1)*100).replace([float('inf'),float('-inf')],0).fillna(0)
    score = ((latest['종가']>ma5).astype(int)*25+(ma5>ma20).astype(int)*25
             +(ratio>=1.5).astype(int)*20+(pos>=75).astype(int)*20+(change>0).astype(int)*10)
    rows=[]
    for code in latest.index:
        r=latest.loc[code]
        rows.append({
            'name':str(r['name']), 'code':str(code), 'market':str(r['market']), 'date':latest_date,
            'price':int(round(float(r['종가']))), 'change':round(float(change.loc[code]),2),
            'value_eok':round(float(r['거래대금'])/1e8,1),
            'close_position':round(float(pos.loc[code]),1),'volume_ratio':round(float(ratio.loc[code]),2),
            'ma5':round(float(ma5.loc[code]),2), 'ma20':round(float(ma20.loc[code]),2),
            'score':int(score.loc[code]),
            'watch':bool(score.loc[code]>=70 and float(r['거래대금'])>=1e10 and 0<float(change.loc[code])<=15 and float(pos.loc[code])>=60),
            'chase_risk':bool(float(change.loc[code])>=15)
        })
    rows.sort(key=lambda x:(-x['score'],-x['value_eok'],x['code']))
    backtest=historical_forward_check(history)
    return {
        'backtest':backtest,
        'asof':latest_date,'updated':now.strftime('%Y-%m-%d %H:%M KST'),
        'version':5, 'minor_version':'5.0', 'source':'FinanceData/marcap',
        'universe_size':int(len(latest)),
        'analyzed_count':len(rows),'history_days':HISTORY_DAYS,'rows':rows,
        'notice':'서드파티 공개 KRX 데이터셋 기반의 장 마감 후 분석. 실시간 시세 아님. 점수는 상승 확률 아님.'
    }



def historical_forward_check(history):
    """15개 과거 마감일의 관찰조건 충족 종목의 다음 거래일 종가 변화.

    후보 추출에 미래 자료를 쓰지 않음. 누락된 다음날 가격은 누락으로 세며
    생존 종목만의 성과로 오인되지 않게 결과에서 명시한다.
    이 수치는 모의 매매 성과(체결/비용/미끄러짐)가 아니다.
    """
    import statistics
    daily=[]; all_returns=[]; missing=0; total_selected=0
    begin=max(20,len(history)-1-BACKTEST_DAYS)
    for idx in range(begin,len(history)-1):
        date, frame = history[idx]
        window=history[idx-20:idx+1]
        c=pd.concat([f['종가'].rename(d) for d,f in window],axis=1)
        v=pd.concat([f['거래량'].rename(d) for d,f in window],axis=1)
        valid=(c.notna().all(axis=1)&(c>0).all(axis=1)&v.notna().all(axis=1)&(v.iloc[:,:-1]>0).all(axis=1))
        current=frame.loc[frame.index.intersection(c.index[valid])].copy()
        if current.empty:
            continue
        c=c.loc[current.index];v=v.loc[current.index]
        ma5=c.iloc[:,-5:].mean(axis=1);ma20=c.iloc[:,-20:].mean(axis=1)
        volratio=v.iloc[:,-1]/v.iloc[:,:-1].mean(axis=1)
        rng=(current['고가']-current['저가']).replace(0,float('nan'))
        position=((current['종가']-current['저가'])/rng*100).fillna(50)
        change=(current['종가']/c.iloc[:,-2]-1)*100
        score=((current['종가']>ma5).astype(int)*25+(ma5>ma20).astype(int)*25
               +(volratio>=1.5).astype(int)*20+(position>=75).astype(int)*20
               +(change>0).astype(int)*10)
        eligible=current[(score>=70)&(current['거래대금']>=1e10)&(change>0)&(change<=15)&(position>=60)].copy()
        eligible['score']=score.reindex(eligible.index)
        eligible=eligible.sort_values(['score','거래대금'],ascending=False).head(BACKTEST_TOP_N)
        next_day,next_frame=history[idx+1]
        returns=[]
        for code,row in eligible.iterrows():
            total_selected+=1
            if code not in next_frame.index:
                missing+=1
                continue
            next_close=next_frame.loc[code,'종가']
            if not pd.notna(next_close) or next_close<=0:
                missing+=1
                continue
            pct=(float(next_close)/float(row['종가'])-1)*100
            returns.append(pct);all_returns.append(pct)
        daily.append({'date':date,'next_date':next_day,
                      'selected':int(len(eligible)),'observed':len(returns),
                      'mean_pct':round(statistics.mean(returns),2) if returns else None,
                      'win_rate_pct':round(sum(x>0 for x in returns)*100/len(returns),1) if returns else None})
    return {
      'method':'전일 종가 후보 추출 → 다음 거래일 종가 수익률(종가 대비). 매수/매도 체결을 가정하지 않음.',
      'days':len(daily),'selected':total_selected,'observed':len(all_returns),'missing_next_day':missing,
      'average_pct':round(statistics.mean(all_returns),2) if all_returns else None,
      'median_pct':round(statistics.median(all_returns),2) if all_returns else None,
      'win_rate_pct':round(sum(x>0 for x in all_returns)*100/len(all_returns),1) if all_returns else None,
      'by_day':daily,
      'criteria':'당일 점수 70점 이상, 거래대금 100억원 이상, 상승률 0~15%, 종가 위치 60% 이상 중 점수·거래대금 순 10종목',
      'caution':'과거 조건부 표본의 기술통계이며 미래 수익률 예측 아님. 거래비용·세금·매매 슬리피지·실제 체결 가능성을 반영하지 않음. 다음날 가격이 없는 종목은 결측으로 별도 집계.'
    }


def main():
    now = dt.datetime.now(KST)
    reference=expected_trading_date(now)
    data=get_data(reference)
    result=analyze(data,now)
    actual=dt.date.fromisoformat(result['asof'])
    lag=trading_day_gap(actual,reference)
    if lag > MAX_LAG_SESSIONS:
        raise RuntimeError(f'마지막 데이터 {actual}가 기대 거래일 {reference}보다 {lag}거래일 늦습니다. 기존 배포 유지.')
    result.update({
        'expected_asof':reference.isoformat(),
        'lag_sessions':lag,
        'data_status':'delayed' if lag else 'current',
        'freshness_message':(
            f'원본 제공이 {lag}거래일 지연됨. {actual} 기준 과거 기록이며 당일 종가매매 판단에 사용 금지.'
            if lag else '현재 확인 가능한 최근 마감 거래일 데이터셋이 반영됨.'
        ),
    })
    if lag:
        log.warning('주의: %s (기대 거래일 %s)',result['freshness_message'],reference)
    tmp=OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    os.replace(tmp,OUT)
    log.info('분석 완료: 원천 %s 기준일=%s 전체=%d 분석유효=%d',
             result['source'],result['asof'],result['universe_size'],result['analyzed_count'])
    for item in result['rows'][:10]:
        log.info('후보 %s (%s), %s점',item['name'],item['code'],item['score'])

if __name__=='__main__':
    main()
