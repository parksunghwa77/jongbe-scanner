"""Read-only check of alternative NAVER daily stock data.
Does not alter the deployed scanner, scores, or existing data.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import sys

try:
    import FinanceDataReader as fdr
except ImportError:
    print('INSTALL REQUIRED: pip install finance-datareader')
    raise

now = datetime.now(ZoneInfo('Asia/Seoul'))
start = (now - timedelta(days=16)).date().isoformat()
end = (now + timedelta(days=1)).date().isoformat()
stock_list = [('005930', '삼성전자'), ('000660', 'SK하이닉스'), ('441270', '파인엠텍')]
all_results = []
for code, name in stock_list:
    print(f'\n== {name} {code} ==', flush=True)
    try:
        df = fdr.DataReader('NAVER:' + code, start, end)
        if df.empty:
            raise ValueError('Empty dataframe')
        required = ('Open','High','Low','Close','Volume')
        if any(col not in df for col in required):
            raise ValueError('OHLCV column missing: ' + str(list(df.columns)))
        df = df.sort_index()
        last = df.iloc[-1]
        day = df.index[-1].date().isoformat()
        good = (last['Low'] > 0 and last['Low'] <= last['Open'] <= last['High']
                and last['Low'] <= last['Close'] <= last['High'] and last['Volume'] >= 0)
        result = dict(code=code, name=name, asof=day, close=int(last['Close']),
                      open=int(last['Open']), high=int(last['High']),
                      low=int(last['Low']), volume=int(last['Volume']),
                      valid_ohlcv=bool(good), newest_calendar_days_old=(now.date()-df.index[-1].date()).days)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        all_results.append(result)
    except Exception as exc:
        print(f'ERROR {type(exc).__name__}: {exc}', flush=True)
        all_results.append({'code': code, 'name': name, 'error': str(exc)})
print('\nSUMMARY:', json.dumps(all_results, ensure_ascii=False), flush=True)
if any('error' in r or not r['valid_ohlcv'] for r in all_results):
    print('TEST FAIL: At least one price request failed or OHLCV is invalid.', flush=True)
    sys.exit(1)
print('TEST PASS (sample only): All three symbols returned internally consistent OHLCV.', flush=True)
print('Not yet approved for automatic all-market substitution.', flush=True)
