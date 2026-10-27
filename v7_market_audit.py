"""V7 read-only stock universe audit. Fail closed on stale or malformed inputs.

PASS checks internal MARCAP OHLCV consistency, NOT exchange price agreement.
This test never changes deployed scans, results.json, or trading recommendations.
"""
from datetime import datetime, time
from io import BytesIO
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import requests

KST = ZoneInfo("Asia/Seoul")
URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{}.parquet"
FIELDS = ["Date", "Code", "Open", "High", "Low", "Close", "Volume"]


def expected_completed_session(now):
    """Return most recent completed XKRX calendar session, with a conservative 16:00 cutoff."""
    calendar = xcals.get_calendar("XKRX")
    day = pd.Timestamp(now.date())
    cutoff = day if now.time() >= time(16, 0) else day - pd.Timedelta(days=1)
    return calendar.date_to_session(cutoff, direction="previous").date()


def main():
    now = datetime.now(KST)
    expected = expected_completed_session(now)
    frames = []
    for year in (now.year, now.year - 1):
        response = requests.get(URL.format(year), timeout=(15, 90))
        response.raise_for_status()
        frames.append(pd.read_parquet(BytesIO(response.content), columns=FIELDS))

    data = pd.concat(frames, ignore_index=True)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce").dt.normalize()
    data["Code"] = data["Code"].astype(str).str.zfill(6)
    for col in FIELDS[2:]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data[data["Date"].notna() & (data["Date"].dt.date <= now.date())].copy()
    if data.empty:
        raise RuntimeError("No valid dated MARCAP records; test cannot continue")

    source_date = data["Date"].max().date()
    universe = data[data["Date"].dt.date.eq(source_date)].drop_duplicates("Code", keep="last")
    o, h, low, close, volume = (universe[k] for k in FIELDS[2:])
    valid = (o.notna() & h.notna() & low.notna() & close.notna()
             & volume.notna() & (low > 0) & (low <= o) & (o <= h)
             & (low <= close) & (close <= h) & (volume > 0))
    rejected = universe.loc[~valid, ["Code", "Open", "High", "Low", "Close", "Volume"]]
    current = source_date == expected
    eligible = int(valid.sum()) if current else 0

    print("V7 READ-ONLY DATA GATE (not NAVER/exchange price cross-check)")
    print(f"Local run time: {now.isoformat(timespec='seconds')}")
    print(f"Expected completed XKRX session: {expected}; MARCAP snapshot: {source_date}")
    print(f"Source freshness: {'CURRENT' if current else 'STALE / MISMATCH - BLOCK'}")
    print(f"Universe: {len(universe)}; OHLCV PASS: {int(valid.sum())}; FAIL: {len(rejected)}")
    print(f"Eligible for further review: {eligible} (not trade signals)")
    print("Invalid examples (up to 20):")
    print(rejected.head(20).to_string(index=False))
    print("Note: zero-volume and halted securities may be legitimate; excluded from active-trading candidates.")
    print("Note: OHLCV PASS does NOT verify prices against KRX, NAVER or corporate actions.")
    print("No results.json modifications, Pages deployments or trade recommendations.")
    if not current:
        print("DATA GATE BLOCKED: source date is not the expected completed trading session.")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
