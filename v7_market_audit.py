"""Read-only universe-wide MARCAP OHLCV integrity audit (not live trading signals)."""
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
import pandas as pd
import requests

TODAY = datetime.now(ZoneInfo('Asia/Seoul')).date()
URL = 'https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{}.parquet'
FIELDS = ['Date', 'Code', 'Open', 'High', 'Low', 'Close', 'Volume']


def main():
    frames = []
    for year in (TODAY.year, TODAY.year - 1):
        response = requests.get(URL.format(year), timeout=(15, 90))
        response.raise_for_status()
        frames.append(pd.read_parquet(BytesIO(response.content), columns=FIELDS))
    data = pd.concat(frames, ignore_index=True)
    data['Date'] = pd.to_datetime(data['Date'], errors='coerce').dt.normalize()
    for col in FIELDS[2:]:
        data[col] = pd.to_numeric(data[col], errors='coerce')
    data['Code'] = data['Code'].astype(str).str.zfill(6)
    data = data.loc[data['Date'].notna() & (data['Date'].dt.date <= TODAY)]
    if data.empty:
        raise RuntimeError('MARCAP: no usable records')
    latest = data['Date'].max()
    universe = data.loc[data['Date'].eq(latest)].drop_duplicates('Code', keep='last')
    o, h, l, c, v = (universe[col] for col in ('Open', 'High', 'Low', 'Close', 'Volume'))
    valid = (o.notna() & h.notna() & l.notna() & c.notna() & v.notna()
             & (l > 0) & (l <= o) & (o <= h) & (l <= c) & (c <= h) & (v > 0))
    rejected = universe.loc[~valid, ['Code', 'Open', 'High', 'Low', 'Close', 'Volume']]
    print('V7 READ-ONLY MARCAP UNIVERSE AUDIT (not NAVER cross-check)')
    print(f'Run date KST: {TODAY}; MARCAP latest session: {latest.date()}')
    print(f'Universe: {len(universe)}; PASS: {int(valid.sum())}; FAIL: {int((~valid).sum())}')
    print(f'Days since latest record (calendar): {(TODAY - latest.date()).days}')
    print('Rejected examples (max 20):')
    print(rejected.head(20).to_string(index=False))
    if (TODAY - latest.date()).days > 3:
        print('WARNING: MARCAP snapshot may be stale.')
    print('PASS means OHLCV internal consistency only, NOT verified exchange prices.')
    print('No trade recommendations, results.json writes, or website deployments.')


if __name__ == '__main__':
    main()
