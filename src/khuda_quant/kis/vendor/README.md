# vendor — open-trading-api 예제 원본

- 출처: https://github.com/koreainvestment/open-trading-api
- 커밋: `SOURCE_COMMIT`  (2026-11-16)
- 복사 위치: `examples_llm/kis_auth.py`, `examples_llm/domestic_stock/<이름>/<이름>.py`
- 참고를 위한 원본과 동일 내용 (예제의 `import kis_auth as ka`가 그대로 동작).
- 인자 예시는 원본 저장소의 `chk_<이름>.py`를 참고

| 파일 | 용도 |
|---|---|
| `kis_auth.py` | 인증·토큰, 공통 호출. import할 때 `~/KIS/config/kis_devlp.yaml`을 읽는다 |
| `chk_holiday.py` | 국내 휴장일 조회 |
| `inquire_balance.py` | 잔고 조회 |
| `inquire_psbl_order.py` | 주문 가능 금액 조회 |
| `order_cash.py` | 현금 주문 (매수·매도) |
| `inquire_daily_ccld.py` | 일별 주문·체결 조회 |
| `order_rvsecncl.py` | 주문 정정·취소 |

## 수정 기록

현재 수정 없음.
