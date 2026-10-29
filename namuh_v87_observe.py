"""NHPLUG 현재가 스냅샷 자동 관찰. 1분봉 생성/조회가 아님. 주문 없음.

사용자 API 비밀키는 GitHub Actions Secrets에서만 읽으며, GitHub Pages에 올리지 않음.
예약 실행 지연을 기록하고, 시간을 벗어나면 시세를 수집하지 않음.
"""
import csv
import json
import os
import re
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

KST=ZoneInfo('Asia/Seoul')
TARGETS={'09:15':time(9,15),'09:30':time(9,30),'09:45':time(9,45),'10:15':time(10,15)}
DEFAULT=['005930','000660','009150','042700','403870','240810','095610','084110','200670','035420','006400','105560']
MAX_STOCKS=30

def in_session(day):
    import exchange_calendars
    return bool(exchange_calendars.get_calendar('XKRX').is_session(day.isoformat()))

def eligible(now,target):
    t=TARGETS[target]; minutes=(now.hour*60+now.minute)-(t.hour*60+t.minute)
    return in_session(now.date()) and 0 <= minutes <= 2

def read_candidates():
    # 1~30종목만 점검. 사용자의 데이터 전체·잔고·주문내역은 수집하지 않음.
    codes=list(DEFAULT)
    path=Path('v6-scores.json')
    if path.exists():
        try:
            obj=json.loads(path.read_text())
            for row in obj.get('rows',[]):
                code=str(row.get('code','')).zfill(6)
                if re.fullmatch(r'\d{6}',code) and code not in codes:
                    codes.append(code)
                if len(codes)>=MAX_STOCKS:break
        except (OSError,ValueError,AttributeError,TypeError):pass
    return codes[:MAX_STOCKS]

def main():
    now=datetime.now(KST)
    target=os.getenv('TARGET_TIME','09:15')
    if target not in TARGETS:raise SystemExit('허용되지 않은 관찰 시각')
    print(f'대상 시각={target}; 시작시각={now.isoformat(timespec="seconds")}')
    if not eligible(now,target):
        print('휴장일 또는 GitHub Actions 예약 실행 지연: 관찰 자료 생성하지 않음')
        return
    if not os.getenv('NHPLUG_APP_KEY') or not os.getenv('NHPLUG_APP_SECRET'):
        raise SystemExit('나무증권 Secrets 미설정: 자료 생성하지 않음')
    from nhplug import call
    folder=Path('minute-observations');folder.mkdir(exist_ok=True)
    dest=folder/f'{now.date().isoformat()}-{target.replace(":", "")}.csv'
    data=[]
    for code in read_candidates():
        requested=datetime.now(KST)
        try:
            response=call('/krstock/quote/v1/currentPrice',{'iem_cd':code,'market_cd':'UNT'})
            observed=datetime.now(KST)
            row=response.get('Output_0') if isinstance(response,dict) else None
            if isinstance(row,list):row=row[0] if row else None
            price=row.get('stck_prpr') if isinstance(row,dict) else None
            if price is None or not re.fullmatch(r'\d+(?:\.\d+)?',str(price)) or float(price)<=0:
                continue
            # 작업 조회시각만 알 수 있음; 실제 거래시각 / KRX 전용 시세 여부 미검증.
            data.append({'date':now.date().isoformat(),'code':code,'target_time':target,
                         'requested_at_kst':requested.isoformat(timespec='seconds'),
                         'response_at_kst':observed.isoformat(timespec='seconds'),
                         'quote_price':price,'kind':'NHPLUG_UNT_CURRENT_PRICE_SNAPSHOT_NOT_MINUTE_OPEN'})
        except Exception:
            # 외부 API 원문이나 인증 정보가 로그에 남지 않게 상세 예외 출력 금지.
            print(f'{code}: API 조회 실패 (민감정보 비출력)')
    if not data:
        print('유효한 응답 없음; 빈 가격 파일 생성하지 않음')
        return
    with dest.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=data[0].keys());writer.writeheader();writer.writerows(data)
    print(f'관찰 데이터 {len(data)}종목; 실제 API 체결시각 불명; 정확한 1분봉 시가 아님')

if __name__=='__main__':main()
