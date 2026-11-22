# KHUDA 10th finance — khuda-quant

국내 주식·ETF를 일봉 기준으로 주간 리밸런싱 하는 것으로 잡음.
운용금 약 200만원, 주문·체결은 한국투자증권 KIS Open API를 활용함.



## 규칙

1. 새 파일(.py, .sql)은 처음 작성할 때 30줄 이하로 시작한다. 기능을 늘리며 길어지는 것은 괜찮다.
2. KIS 호출은 [open-trading-api](https://github.com/koreainvestment/open-trading-api) 예제에서 시작한다.
   예제는 `src/khuda_quant/kis/vendor/`에 원본 그대로 두고, 우리 코드는 vendor 밖(`kis/client.py`, `kis/kis_broker.py`)에서 호출한다.
3. 환경변수(KIS 키·계좌번호, KRX 로그인, Slack 주소)는 모두 `.env` 하나로 관리하고 커밋하지 않는다. 항목은 `.env.example` 참고.
   vendor의 `kis_auth.py`는 `~/KIS/config/kis_devlp.yaml`을 읽으므로 `kis/client.py`가 `.env` 값으로 그 파일을 만들어 준다.
4. 실제 KIS 키로 실행하는 것은 담당자가 직접 한다.

## 흐름

연구와 운용은 따로 실행된다. 둘이 공유하는 것은 `strategy/`의 전략 코드뿐이다.

```
[연구] 사람이 필요할 때 반복 실행
  jobs/fetch_prices.py : 시세 수집(FinanceDataReader) → 검증 → Parquet 저장
  jobs/backtest.py     : 전략 선택 → 목표 비중(target_weight) → bt 백테스트 → 비교·검증
                         → 확정되면 config/settings.yaml의 strategy 항목을 고쳐 커밋

[운용] systemd timer가 매주 월요일 실행(추후 전략팀의 계획에 따라 리밸런싱일 변경)
  market_day (ExecCondition) : 거래일·시간 판단 + 휴장일 대조(chk_holiday), 건너뛰면 사유를 SQLite에 기록
  jobs/rebalance.py    : 실행 잠금 → 미체결·이전 상태 정리 → 시세 갱신 → 확정 전략으로 목표 비중
                         → 잔고 조회 → 정수 주 주문 계획 → 사전 점검 → 매도 → 체결 확인
                         → 주문 가능 금액 재조회 → 매수 재계산 → 사전 점검 → 매수 → 체결 확인
                         → 미체결 처리 → 사후 대조 → SQLite 기록 → 알림

[운용] systemd timer가 평일 장 마감 뒤 실행 (주문 없음)
  jobs/daily.py        : 사후 대조 → 리밸런싱 누락 감시 → 일일 보고
```

주문은 응답이 없어도 접수됐을 수 있으므로 자동으로 다시 보내지 않는다. 요청 전에 SQLite에 먼저 기록하고, 체결 조회로 미접수를 확인한 뒤에만 재전송한다.

처음 운용을 시작할 때도 `rebalance.py`를 그대로 씀(보유 0 → 목표 비중만큼 매수하는 식으로 동작).

## 폴더 구조

```
config/                 휴장일(krx_holidays.toml), 운용 설정·확정 전략(settings.yaml)
deploy/systemd/         service, timer, 설치 스크립트
docs/                   구현 계획(planning.md), 진행 기록(progress.md), architecture/(구조도·설계 문서)
jobs/                   실행 진입점: fetch_prices·backtest(연구), rebalance·daily(운용)
tests/                  pytest
data/market/            Parquet 시세 raw/(원본)·std/(표준) (커밋 안 함)
src/khuda_quant/
  market_day.py         거래일 판단
  data/                 schema, fetchers, validators, storage
  strategy/             core(공통 규칙), universe·risk(공통 단계), momentum 등 전략 후보 파일
  backtest/             run_bt (bt), metrics (성과·검증)
  execution/            order_planner, risk_gate, broker, fill_tracker, reconcile
  kis/                  client, kis_broker, vendor/(open-trading-api 예제 원본)
  store/                schema.sql, db (SQLite)
  reporting/            notifier (Slack)
```

## 구성 요소 ↔ 파일

| 구성 요소 | 파일 |
|---|---|
| 시세 표준 스키마 | `src/khuda_quant/data/schema.py` |
| 시세 수집 | `src/khuda_quant/data/fetchers.py` |
| 검증 | `src/khuda_quant/data/validators.py` |
| Parquet 저장 | `src/khuda_quant/data/storage.py` |
| 전략 공통 규칙 | `src/khuda_quant/strategy/core.py` |
| 투자 대상·비중 조정 (공통 단계) | `src/khuda_quant/strategy/universe.py`, `risk.py` |
| 전략 후보 (alpha·portfolio → target_weight) | `src/khuda_quant/strategy/momentum.py` 등 `strategy/<이름>.py` |
| 확정 전략 지정 | `config/settings.yaml`의 `strategy` |
| bt 백테스트 | `src/khuda_quant/backtest/run_bt.py` |
| 성과·검증 | `src/khuda_quant/backtest/metrics.py` |
| systemd timer | `deploy/systemd/rebalance.timer`·`.service`(주간), `daily.timer`·`.service`(평일), `install.sh` |
| 거래일 판단 | `src/khuda_quant/market_day.py`, `config/krx_holidays.toml` |
| 잔고 조회·주문 | `src/khuda_quant/execution/broker.py`, `src/khuda_quant/kis/kis_broker.py` |
| 체결 확인·미체결 처리 | `src/khuda_quant/execution/fill_tracker.py` (정책은 `settings.yaml`의 `execution`) |
| 사후 대조 | `src/khuda_quant/execution/reconcile.py` |
| KIS 호출 | `src/khuda_quant/kis/client.py`, `src/khuda_quant/kis/vendor/` |
| 정수 주 주문 계획 | `src/khuda_quant/execution/order_planner.py` |
| 사전 점검 | `src/khuda_quant/execution/risk_gate.py` |
| SQLite 기록 | `src/khuda_quant/store/schema.sql`, `src/khuda_quant/store/db.py` |
| 알림 | `src/khuda_quant/reporting/notifier.py` |
| 시세 수집 실행 [연구] | `jobs/fetch_prices.py` |
| 백테스트 실행 [연구] | `jobs/backtest.py` |
| 리밸런싱 실행 [운용] | `jobs/rebalance.py` |
| 사후 대조·누락 감시·일일 보고 [운용] | `jobs/daily.py` |
| 운용 설정 (한도·비용·확정 전략·체결 정책·알림 대상) | `config/settings.yaml`, `.env.example` |

## 시작하기 (uv)

```bash
uv sync                    # .venv 생성, 의존성 설치
cp .env.example .env       # 키·계좌·Slack 주소 입력
uv run pytest              # 테스트
uv run python jobs/fetch_prices.py 005930 --start 2026-11-19 --end 2026-11-20  # 시세 수집
uv run python jobs/backtest.py --strategy momentum            # 전략 검증
uv run --env-file .env python jobs/rebalance.py --env paper   # .env를 읽어 실행
```

## 1주차 운영 기능 확인

거래일 계산(`is_trading_day`, `next_trading_day`), 2026년 휴장일,
SQLite 스키마 적용·트랜잭션·백업을 로컬에서 검증할 수 있다.
거래일 함수는 `datetime.date`를 받으며 목록이 없는 연도는 `LookupError`로 멈춘다.
테스트는 임시 DB를 사용하고 외부 API를 호출하지 않는다.

```bash
uv run pytest -q tests/test_market_day.py tests/test_store.py
```

현재 PC에 준비한 환경에서는 PowerShell로 다음 명령을 실행해도 된다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

DB 사용법과 스키마 결정 사항은 `docs/progress.md`의 26.11.20. 기록을 참고한다.

## 아직 구현하지 않은 것

전략·주문 모듈, 운용 설정 값, KIS 인증·휴장일 대조,
ExecCondition 시간대 판단·건너뜀 기록, 리밸런싱·알림·서버 배포는 후속 구현 대상이다.
