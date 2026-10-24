"""종베 스캐너: 무료 Yahoo Finance 일봉 데이터 기반 시범 분석.
실시간 시세나 투자 자문이 아닙니다.
"""
import datetime as dt
import json
import pathlib
import time

import pandas as pd
import yfinance as yf

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "results.json"
KST = dt.timezone(dt.timedelta(hours=9))
# 분석 범위: 15개 시범 종목. 코스피=.KS / 코스닥=.KQ
STOCKS = {
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스",
    "035420.KS": "NAVER", "005380.KS": "현대차",
    "068270.KS": "셀트리온", "105560.KS": "KB금융",
    "006400.KS": "삼성SDI", "051910.KS": "LG화학",
    "247540.KQ": "에코프로비엠", "086520.KQ": "에코프로",
    "042700.KS": "한미반도체", "403870.KQ": "HPSP",
    "058470.KQ": "리노공업", "240810.KQ": "원익IPS",
    "095340.KQ": "ISC",
}


def analyze(ticker, name, df):
    if df is None or df.empty:
        raise ValueError("조회 결과 없음")
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    required = ("Close", "High", "Low", "Volume")
    df = df.dropna(subset=list(required)).sort_index()
    if len(df) < 25:
        raise ValueError(f"일봉 부족: {len(df)}개")
    last, prev = df.iloc[-1], df.iloc[-2]
    close, high, low, vol = (float(last[k]) for k in required)
    prior = float(prev["Close"])
    if close <= 0 or prior <= 0 or high < low or vol < 0:
        raise ValueError("가격/거래량 데이터 이상")
    ma5 = float(df["Close"].tail(5).mean())
    ma20 = float(df["Close"].tail(20).mean())
    avgvol = float(df["Volume"].iloc[-21:-1].mean())
    ratio = vol / avgvol if avgvol > 0 else 0.0
    position = (close-low) / (high-low) * 100 if high > low else 50
    change = (close/prior-1)*100
    score = sum((25 if close>ma5 else 0, 25 if ma5>ma20 else 0,
                 20 if ratio>=1.5 else 0, 20 if position>=75 else 0,
                 10 if change>0 else 0))
    last_ts = pd.Timestamp(df.index[-1])
    return {
        "name": name, "code": ticker.split(".")[0],
        "date": last_ts.strftime("%Y-%m-%d"),
        "price": round(close), "change": round(change, 2),
        "value_eok": round(close * vol / 1e8, 1),
        "close_position": round(position, 1),
        "volume_ratio": round(ratio, 2), "score": score,
        "target": round(close * 1.03), "stop": round(close * .98),
    }


def download_one(ticker):
    # 공개 무료 데이터는 간헐적 제한/지연이 있습니다.
    last_exc = None
    for attempt in range(2):
        try:
            df = yf.download(
                ticker, period="4mo", interval="1d",
                auto_adjust=False, progress=False, threads=False,
                timeout=20,
            )
            if df is None or df.empty:
                raise ValueError("조회 결과 없음")
            return df
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.5)
    raise ValueError(str(last_exc))


def main():
    rows, errors = [], []
    for ticker, name in STOCKS.items():
        try:
            result = analyze(ticker, name, download_one(ticker))
            rows.append(result)
            print(f"OK {ticker} {result['date']} {result['score']}점")
        except Exception as exc:
            msg = f"{ticker} {name}: {str(exc)[:160]}"
            errors.append(msg)
            print("WARN", msg)
        time.sleep(.25)
    rows.sort(key=lambda x:(-x["score"],-x["value_eok"]))
    asof = max((row["date"] for row in rows), default=None)
    payload = {
        "asof":asof,
        "updated":dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "rows":rows[:10],
        "analyzed_count":len(rows),
        "universe_size":len(STOCKS),
        "errors":errors,
        "notice":"15개 시범 종목·지연 일봉. 거래대금은 종가×거래량 추정치.",
    }
    if not rows:
        # 실패한 데이터로 기존 정상 결과를 덮어쓰지 않습니다.
        raise RuntimeError("분석 성공 종목 0개. Yahoo Finance 연결/조회 결과를 확인하세요. " + "; ".join(errors[:3]))
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n", encoding="utf8")
    print(f"결과 저장: {len(rows)}개 분석, 상위 {len(payload['rows'])}개, 오류 {len(errors)}개")

if __name__ == "__main__":
    main()
