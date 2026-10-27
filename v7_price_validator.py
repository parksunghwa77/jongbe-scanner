"""Read-only NAVER OHLCV diagnostic for the Jongbe Scanner V7 branch.

This script prints test results only. It does not modify results.json,
scanner.py, or the deployed website. Data provider values are not treated as
verified exchange prices or trading recommendations.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd

KST = ZoneInfo("Asia/Seoul")
STOCKS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "441270": "파인엠텍",
    "145210": "데이터 이상 점검",
}


def validate_stock(code: str, name: str) -> None:
    today = datetime.now(KST).date()
    start = today - timedelta(days=15)
    try:
        df = fdr.DataReader(
            "NAVER:" + code,
            start.isoformat(),
            (today + timedelta(days=1)).isoformat(),
        ).sort_index()
        if df.empty:
            print(f"{name} ({code}): FAIL - 데이터 없음")
            return

        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            print(f"{name} ({code}): FAIL - 누락된 열: {missing}")
            return

        latest_date = pd.Timestamp(df.index[-1]).date()
        values = pd.to_numeric(df.iloc[-1][required], errors="coerce")
        o, h, low, close, volume = values.tolist()
        valid = bool(
            values.notna().all()
            and low > 0
            and low <= o <= h
            and low <= close <= h
            and volume > 0
        )
        print(
            f"{name} ({code}) | 기준일: {latest_date} | "
            f"종가: {close:,.0f} | 거래량: {volume:,.0f} | "
            f"기본 검증: {'PASS' if valid else 'FAIL'}"
        )
        # Calendar-day threshold is a warning only, not a trading-day validator.
        if (today - latest_date).days > 3:
            print("WARNING: 최신 데이터 지연 가능성 (휴장일 여부 별도 확인 필요)")
        if not valid:
            print("WARNING: OHLCV 값이 비정상적이므로 매매 판단에 사용하지 마세요")
    except Exception as exc:
        print(f"{name} ({code}): ERROR - {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    for stock_code, stock_name in STOCKS.items():
        validate_stock(stock_code, stock_name)
