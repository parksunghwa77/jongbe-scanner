"""종베 스캐너 v4: KRX 코스피·코스닥 전종목 **확정 일봉** 스캔.

GitHub Actions에서 ``python scanner.py`` 로 실행. 기존 v3의 workflow를 그대로 사용.
무료 스크래핑 소스는 변경/차단될 수 있으며, 그런 경우 성공한 척하지 않고 실패한다.
장중 실시간 분석 및 매수·매도 추천이 아니다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results.json'
KST = ZoneInfo('Asia/Seoul')
REQUIRED = ('시가', '고가', '저가', '종가', '거래량', '거래대금', '등락률')
MARKETS = ('KOSPI', 'KOSDAQ')
HISTORY_DAYS = 21  # 금일 1일 + 이전 20거래일
MAX_CALENDAR_LOOKBACK = 65
MAX_STALE_CALENDAR_DAYS = 10
MIN_MARKET_CODES = {'KOSPI': 400, 'KOSDAQ': 500}
MIN_VALID_MARKET_TRADES = {'KOSPI': 200, 'KOSDAQ': 200}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('jongbe')


def last_eligible_date(now: dt.datetime) -> dt.date:
    """장 마감 확정값 보수적으로 취급: 16:30 KST 이전에는 전날부터 탐색."""
    local = now.astimezone(KST)
    date = local.date()
    if local.time() < dt.time(16, 30):
        date -= dt.timedelta(days=1)
    return date


def fetch_snapshot(date: dt.date, market: str) -> pd.DataFrame | None:
    """pykrx의 전종목 일봉 스냅샷 1일치 수집. 휴장일이면 None."""
    from pykrx import stock

    day = date.strftime('%Y%m%d')
    errors = []
    for attempt in range(2):
        try:
            raw = stock.get_market_ohlcv_by_ticker(day, market=market)
            if raw is None or raw.empty:
                return None  # 휴장일 또는 데이터 미제공
            if not set(REQUIRED).issubset(raw.columns):
                raise ValueError(f'필수 열 없음: {set(REQUIRED) - set(raw.columns)}')
            frame = raw.loc[:, REQUIRED].copy()
            frame.index = frame.index.map(str).str.zfill(6)
            for col in REQUIRED:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')
            if len(frame) < MIN_MARKET_CODES[market]:
                raise ValueError(f'{market} 종목 수 비정상: {len(frame)}')
            good = ((frame['종가'] > 0) & (frame['거래량'] > 0)).sum()
            if good < MIN_VALID_MARKET_TRADES[market]:
                raise ValueError(f'{market} 정상 거래 종목 수 부족: {good}')
            frame['market'] = market
            return frame
        except Exception as exc:
            errors.append(str(exc)[:150])
            if attempt == 0:
                time.sleep(1.5)
    log.warning('조회 오류 %s %s: %s', day, market, '; '.join(errors))
    return None


def get_complete_market_days(today: dt.date, loader=fetch_snapshot) -> list[tuple[str, pd.DataFrame]]:
    """코스피·코스닥 양쪽 모두 유효한 확정 스냅샷인 날만 21일 수집."""
    history = []
    for lag in range(MAX_CALENDAR_LOOKBACK + 1):
        target = today - dt.timedelta(days=lag)
        if target.weekday() >= 5:
            continue
        a = loader(target, 'KOSPI')
        b = loader(target, 'KOSDAQ')
        if a is None or b is None:
            log.info('%s 건너뜀 (휴장일/수집 실패)', target)
            continue
        full = pd.concat([a, b], axis=0)
        if full.index.has_duplicates:
            raise RuntimeError(f'{target}: 양 시장에서 중복 티커 코드 발견')
        history.append((target.isoformat(), full))
        log.info('%s: KOSPI %d, KOSDAQ %d 종목 수집 (%d/%d)', target, len(a), len(b), len(history), HISTORY_DAYS)
        if len(history) == HISTORY_DAYS:
            break
        # 연속 요청 완화
        time.sleep(0.30)
    if len(history) != HISTORY_DAYS:
        raise RuntimeError(f'전체 시장 확정 데이터 {HISTORY_DAYS}일 필요, {len(history)}일만 수집됨. 기존 배포 유지.')
    history.reverse()  # 오래된 날짜 -> 최신 날짜
    latest = dt.date.fromisoformat(history[-1][0])
    if (today - latest).days > MAX_STALE_CALENDAR_DAYS:
        raise RuntimeError(f'자료 기준일이 오래됨: {latest}. 기존 배포 유지.')
    return history


def compute_scores(history: list[tuple[str, pd.DataFrame]], names: dict[str, str] | None = None, min_valid: int = 500) -> dict:
    """모든 시장 상장 보통/우선주 등 주식 대상 기술 조건을 100점으로 산출."""
    if len(history) < HISTORY_DAYS:
        raise ValueError('21개의 확정 거래일 데이터가 필요함')
    names = names or {}
    latest_date, latest = history[-1]
    # 모든 종목의 21거래일 시세를 티커별로 정렬한 DataFrame으로 구성
    close = pd.concat([frame['종가'].rename(day) for day, frame in history], axis=1)
    volume = pd.concat([frame['거래량'].rename(day) for day, frame in history], axis=1)
    valid = close.notna().all(axis=1) & (close > 0).all(axis=1) & volume.notna().all(axis=1)
    close = close.loc[valid]
    volume = volume.loc[valid]
    latest = latest.loc[latest.index.intersection(close.index)].copy()
    # 건전한 최근 거래 데이터 조건: 거래정지, 시세이상, 구간 이상치 제외
    latest = latest.loc[(latest['종가'] > 0) & (latest['고가'] >= latest['저가'])
                        & (latest['거래량'] > 0) & (latest['거래대금'] > 0)]
    close = close.loc[latest.index]
    volume = volume.loc[latest.index]
    if len(latest) < min_valid:
        raise RuntimeError(f'유효 일봉 종목 {len(latest)}개로 비정상적으로 적음. 데이터 수집 실패 가능성.')

    ma5 = close.iloc[:, -5:].mean(axis=1)
    ma20 = close.iloc[:, -20:].mean(axis=1)
    prev_vol = volume.iloc[:, :-1].mean(axis=1)
    ratio = (latest['거래량'] / prev_vol.where(prev_vol > 0)).fillna(0.0)
    close_position = ((latest['종가'] - latest['저가']) * 100 /
                      (latest['고가'] - latest['저가']).replace(0, float('nan'))).fillna(50.0).clip(0, 100)
    change = latest['등락률'].fillna(0.0)
    scores = ((latest['종가'] > ma5).astype(int) * 25
              + (ma5 > ma20).astype(int) * 25
              + (ratio >= 1.5).astype(int) * 20
              + (close_position >= 75).astype(int) * 20
              + (change > 0).astype(int) * 10)
    rows = []
    for code in latest.index:
        curr = latest.loc[code]
        rows.append({
            'name': str(names.get(code) or code),
            'code': code, 'market': str(curr['market']), 'date': latest_date,
            'price': int(round(float(curr['종가']))),
            'change': round(float(change.loc[code]), 2),
            'value_eok': round(float(curr['거래대금']) / 1e8, 1),  # KRX 실제 거래대금
            'close_position': round(float(close_position.loc[code]), 1),
            'volume_ratio': round(float(ratio.loc[code]), 2),
            'ma5': round(float(ma5.loc[code]), 2),
            'ma20': round(float(ma20.loc[code]), 2),
            'score': int(scores.loc[code]),
        })
    rows.sort(key=lambda x: (-x['score'], -x['value_eok'], x['code']))
    return {
        'asof': latest_date,
        'rows': rows,
        'universe_size': int(len(history[-1][1])),
        'analyzed_count': len(rows),
        'history_days': HISTORY_DAYS,
        'notice': 'KRX 확정 일봉 기반. 거래대금은 실제 누적 체결액. 장중/실시간 검색 아님. 점수는 상승확률 아님.',
    }


def fetch_names_for_display(date: str, important_codes: list[str]) -> dict[str, str]:
    """우선 KRX 전종목 명칭 한 번에 수집, 불가 시 상위 종목만 조회."""
    from pykrx import stock
    names = {}
    try:
        # pykrx 내부 KRX 래퍼. 버전 변경으로 미지원일 경우 안전하게 fallback.
        from pykrx.website.krx.market import wrap
        for market in MARKETS:
            s = wrap.get_market_ticker_and_name(date.replace('-', ''), market)
            if s is None or s.empty:
                raise ValueError(market + ' 종목명 조회 비어 있음')
            names.update({str(code).zfill(6): str(name) for code, name in s.items()})
        log.info('종목명 %d개 확보', len(names))
    except Exception as exc:
        log.warning('전종목 종목명 조회 실패: %s', exc)
        for code in important_codes[:30]:
            try:
                name = stock.get_market_ticker_name(code)
                if name:
                    names[code] = str(name)
            except Exception:
                pass
    return names


def main():
    now = dt.datetime.now(KST)
    today = last_eligible_date(now)
    history = get_complete_market_days(today)
    preliminary = compute_scores(history)
    # 전체 종목명을 취득하되 종목명 API 불안정해도 분석 자체는 성공하도록 설계
    names = fetch_names_for_display(preliminary['asof'], [x['code'] for x in preliminary['rows']])
    result = compute_scores(history, names)
    result['updated'] = now.strftime('%Y-%m-%d %H:%M KST')
    result['version'] = 4
    # 모든 데이터를 생성한 후 원자적 교체. 실패한 수집 결과로 기존 데이터를 덮지 않음.
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    os.replace(tmp, OUT)
    log.info('성공: 기준일=%s, 전체=%d, 유효=%d, 종목명=%d, 파일=%d bytes',
             result['asof'], result['universe_size'], result['analyzed_count'], len(names), OUT.stat().st_size)
    for item in result['rows'][:10]:
        log.info('상위 후보: %s %s 점수=%d 거래대금=%.1f억원', item['name'], item['code'], item['score'], item['value_eok'])


if __name__ == '__main__':
    main()
